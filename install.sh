#!/usr/bin/env bash
# Project Athena installer.  Run on a fresh Ubuntu Server:   sudo ./install.sh
# Safe to run again: it never replaces an existing .env (your database password and
# encryption key), and it skips steps that are already done.
set -Eeuo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${ATHENA_DIR:-/opt/athena}"
export LOG_FILE="${LOG_FILE:-/var/log/athena-install.log}"

# shellcheck source=installer/lib/ui.sh
. "$SRC_DIR/installer/lib/ui.sh"
. "$SRC_DIR/installer/lib/validate.sh"
. "$SRC_DIR/installer/lib/config.sh"
. "$SRC_DIR/installer/lib/system.sh"
. "$SRC_DIR/installer/lib/firewall.sh"
. "$SRC_DIR/installer/lib/backupsetup.sh"

trap 'printf "\nThe installer stopped unexpectedly (line %s). Details: %s\nIt is safe to run it again.\n" "$LINENO" "$LOG_FILE" >&2' ERR

VERSION_STR="$(cat "$SRC_DIR/VERSION" 2>/dev/null || echo unknown)"

cat <<BANNER

  Project Athena $VERSION_STR - installer
  ------------------------------------------------------------
  This will set up Athena on this server. It will:
    1. install Docker (the tool that runs Athena),
    2. ask you a few simple questions,
    3. build and start Athena,
    4. turn on a firewall limited to your library network,
    5. schedule nightly cleanup tasks and encrypted backups.
  This setup takes about 10 minutes. Nothing is sent anywhere: Athena has no
  tracking and does not report back to anyone.
BANNER
confirm "Ready to begin?" y || die "Cancelled. Nothing was changed."

: >>"$LOG_FILE" && chmod 600 "$LOG_FILE"

step "1 of 10: Checking this server"
preflight
check_internet
report_encryption
report_dhcp

step "2 of 10: Installing software"
install_packages

step "3 of 10: A few questions"
DETECTED_IP="$(detect_ip || true)"
DETECTED_CIDR="$(detect_cidr || true)"

say ""
say "Staff will open Athena in a web browser at an address you choose."
say "If you do not have a DNS name for this server, just use its IP address."
while :; do
  ATHENA_HOST="${ATHENA_HOST:-$(ask "Address for Athena (name or IP)" "$DETECTED_IP")}"
  valid_host "$ATHENA_HOST" && break
  warn "That does not look like a valid name or IP address. Example: athena.mylibrary.lan or 192.168.1.50"
  [ "${ATHENA_YES:-0}" = "1" ] && die "Invalid ATHENA_HOST."
  unset ATHENA_HOST
done

while :; do
  TZ_CHOICE="${LIBRARY_TIMEZONE:-$(ask "Library time zone" "$(detect_timezone)")}"
  valid_timezone "$TZ_CHOICE" && break
  warn "Unknown time zone. Use the form Region/City, for example America/New_York."
  [ "${ATHENA_YES:-0}" = "1" ] && die "Invalid LIBRARY_TIMEZONE."
  unset LIBRARY_TIMEZONE
done

say ""
say "Reports can follow your fiscal year. Enter the month it STARTS (1=January ... 7=July)."
while :; do
  FY_CHOICE="${FISCAL_YEAR_START_MONTH:-$(ask "Fiscal year start month (1-12)" "7")}"
  valid_month "$FY_CHOICE" && break
  warn "Please enter a number from 1 to 12."
  [ "${ATHENA_YES:-0}" = "1" ] && die "Invalid FISCAL_YEAR_START_MONTH."
  unset FISCAL_YEAR_START_MONTH
done

SSH_IP="$(ssh_client_ip "${SSH_CLIENT:-}")"
[ -n "$SSH_IP" ] || SSH_IP="$(who -m 2>/dev/null | sed -n 's/.*(\([0-9.]*\)).*/\1/p')"
ENABLE_FW=0
if confirm "Turn on the firewall so only your library network can reach this server? (recommended)" y; then
  while :; do
    FW_CIDR="${ATHENA_NETWORK:-$(ask "Your library network (CIDR)" "$DETECTED_CIDR")}"
    if ! valid_cidr "$FW_CIDR"; then
      warn "That is not a valid network. Example: 192.168.1.0/24"
    elif [ -n "$SSH_IP" ] && ! ip_in_cidr "$SSH_IP" "$FW_CIDR"; then
      warn "You are connected from $SSH_IP, which is outside $FW_CIDR. Turning the firewall on would disconnect you. Choose a network that includes $SSH_IP."
    else
      ENABLE_FW=1; break
    fi
    [ "${ATHENA_YES:-0}" = "1" ] && die "Invalid ATHENA_NETWORK."
    unset ATHENA_NETWORK
  done
fi

step "4 of 10: Copying Athena to $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
if [ "$(readlink -f "$SRC_DIR")" != "$(readlink -f "$INSTALL_DIR")" ]; then
  tar -C "$SRC_DIR" --exclude=./.env --exclude=./web/dist --exclude=./web/node_modules -cf - . | tar -C "$INSTALL_DIR" -xf -
  ok "Files copied."
else
  ok "Already running from $INSTALL_DIR."
fi
cd "$INSTALL_DIR"

step "5 of 10: Creating secret settings"
if [ -e .env ]; then
  ok "Found an existing .env - keeping it exactly as it is."
else
  write_env .env.example .env "$ATHENA_HOST" "$TZ_CHOICE" "$FY_CHOICE"
  ok "Created .env with freshly generated passwords and encryption key."
  warn "IMPORTANT: .env holds the keys to your data. Copy it somewhere safe and OFFLINE (e.g. a locked drawer on a USB stick). Without the encryption key, saved 2FA secrets cannot be recovered."
fi

step "6 of 10: Building and starting Athena (slowest step)"
say "Building the web pages..."
docker compose run --rm --user 0:0 web sh -c "npm ci && npm run build" >>"$LOG_FILE" 2>&1 \
  || die "Building the web pages failed. See $LOG_FILE (last lines: $(tail -3 "$LOG_FILE" | tr '\n' ' '))"
ok "Web pages built."
say "Starting the database..."
docker compose up -d --build db >>"$LOG_FILE" 2>&1 || die "Could not start the database. See $LOG_FILE."
for _ in $(seq 1 60); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' athena-db-1 2>/dev/null)" = "healthy" ] && break
  sleep 2
done
[ "$(docker inspect -f '{{.State.Health.Status}}' athena-db-1 2>/dev/null)" = "healthy" ] || die "The database did not become ready. See: docker compose logs db"
say "Preparing database tables..."
docker compose run --rm migrate >>"$LOG_FILE" 2>&1 || die "Database setup failed. See $LOG_FILE."
say "Starting Athena..."
docker compose up -d --build >>"$LOG_FILE" 2>&1 || die "Could not start Athena. See $LOG_FILE."
for _ in $(seq 1 45); do
  curl -fsS --max-time 3 http://127.0.0.1:8000/health >/dev/null 2>&1 && HEALTHY=1 && break
  sleep 2
done
[ "${HEALTHY:-0}" = "1" ] || die "Athena started but is not answering. Run:  cd $INSTALL_DIR && docker compose logs api"
ok "Athena is running and healthy."

step "7 of 10: Firewall"
if [ "$ENABLE_FW" = 1 ]; then apply_firewall "$FW_CIDR"; else warn "Firewall left unchanged. Strongly consider turning it on later."; fi

step "8 of 10: Nightly tasks and the 'athena' command"
install -m 644 installer/files/athena.cron /etc/cron.d/athena
sed -i "s|@INSTALL_DIR@|$INSTALL_DIR|g" /etc/cron.d/athena
install -m 644 installer/files/athena.logrotate /etc/logrotate.d/athena
install -m 755 installer/files/athena /usr/local/bin/athena
sed -i "s|@INSTALL_DIR@|$INSTALL_DIR|g" /usr/local/bin/athena
ok "Installed. Type 'athena help' any time to see what you can do."

step "9 of 10: Encrypted backups"
setup_backups

step "10 of 10: Certificate for staff computers"
CERT_OUT="/root/athena-root-ca.crt"
[ -n "${SUDO_USER:-}" ] && [ -d "/home/$SUDO_USER" ] && CERT_OUT="/home/$SUDO_USER/athena-root-ca.crt"
for _ in $(seq 1 20); do
  docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt "$CERT_OUT" >>"$LOG_FILE" 2>&1 && break
  sleep 2
done
if [ -s "$CERT_OUT" ]; then
  [ -n "${SUDO_USER:-}" ] && chown "$SUDO_USER" "$CERT_OUT" 2>/dev/null || true
  CERT_FP="$(openssl x509 -in "$CERT_OUT" -noout -fingerprint -sha256 | cut -d= -f2)"
  ok "Certificate saved to $CERT_OUT"
else
  warn "Could not export the certificate yet. Later run:  athena cert"
fi

cat <<DONE

  ============================================================
   Athena $VERSION_STR is installed.
  ============================================================
   Open:  https://$ATHENA_HOST   (your browser will warn until
          you install the certificate - see README, 'After install')

   NEXT STEPS
   1. Create the first administrator account (you will be asked
      for a name and password):
          athena create-admin
   2. Copy the certificate file to staff computers:
          ${CERT_OUT:-/root/athena-root-ca.crt}
      Its fingerprint (to confirm you have the right file):
          ${CERT_FP:-run 'athena cert' to see it}
   3. Save a copy of  $INSTALL_DIR/.env  somewhere safe, offline.
   4. Backups run every night (2:45am), encrypted, into /var/backups/athena

   Keep your backup key safe: without it, backups cannot be restored and the data is lost.

   Full log of this install: $LOG_FILE
DONE
