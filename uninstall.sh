#!/usr/bin/env bash
# Project Athena uninstaller. Removes Athena, its database, and everything the installer added.
#
#   sudo ./uninstall.sh                 asks before doing anything
#   sudo ./uninstall.sh --dry-run       shows what WOULD be removed, changes nothing
#
# It never touches: a USB backup drive, your saved backup key, the folder you cloned Athena into,
# Docker itself, or (unless you ask) the backups stored on this server and the firewall.
set -Eeuo pipefail

INSTALL_DIR="${ATHENA_DIR:-/opt/athena}"
CRON_FILE="${CRON_FILE:-/etc/cron.d/athena}"
LOGROTATE_FILE="${LOGROTATE_FILE:-/etc/logrotate.d/athena}"
BIN_ATHENA="${BIN_ATHENA:-/usr/local/bin/athena}"
SBIN_BACKUP="${SBIN_BACKUP:-/usr/local/sbin/athena-backup}"
LIB_DIR="${LIB_DIR:-/usr/local/lib/athena}"
UDEV_RULE="${UDEV_RULE:-/etc/udev/rules.d/99-athena-backup.rules}"
UNIT_FILE="${UNIT_FILE:-/etc/systemd/system/athena-usb-backup.service}"
CONF_DIR="${CONF_DIR:-/etc/athena}"
STATE_DIR="${STATE_DIR:-/var/lib/athena}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/athena}"
USB_MNT="${USB_MNT:-/run/athena-usb}"
LOG_GLOB_DIR="${LOG_GLOB_DIR:-/var/log}"

DRY_RUN=0; ASSUME_YES=0; DELETE_BACKUPS=0; REMOVE_FIREWALL=0
REMOVED=(); ABSENT=()

say()  { printf '%s\n' "$*"; }
note() { printf '[note] %s\n' "$*"; }
run()  { if [ "$DRY_RUN" = 1 ]; then printf '[dry run] %s\n' "$*"; else "$@"; fi; }

usage() {
  cat <<'U'
Usage: sudo ./uninstall.sh [options]
  --dry-run                 show what would be removed; change nothing
  --yes                     do not ask for confirmation (backups and firewall are still kept unless told otherwise)
  --delete-backups          also delete the backups stored on this server (/var/backups/athena)
  --remove-firewall-rules   also remove the firewall rules for web access (ports 80 and 443)
  -h, --help                this text
U
}

# ---------- safety ----------

# Refuse to delete anything that does not look like an Athena install.
is_safe_install_dir() {
  local d="${1:-}"
  case "$d" in ""|"/"|"/opt"|"/usr"|"/usr/local"|"/etc"|"/var"|"/home"|"/root"|"/bin"|"/sbin"|"/lib"|"/boot") return 1 ;; esac
  [[ "$d" == /* ]] || return 1
  [ "$(awk -F/ '{print NF-1}' <<<"$d")" -ge 2 ] || return 1
  [ -f "$d/docker-compose.yml" ] && [ -f "$d/VERSION" ] && [ -d "$d/installer" ]
}

# stdin: 'ufw status numbered'. stdout: numbers of Athena's web rules, highest first (so deleting one does not shift the rest).
athena_ufw_rule_numbers() {
  sed -nE 's/^\[ *([0-9]+)\] +(80,443\/tcp|443\/udp)( |\().*/\1/p' | sort -rn
}

remove_path() { # path description
  local p="$1"
  if [ -e "$p" ] || [ -L "$p" ]; then
    if run rm -rf -- "$p"; then REMOVED+=("$2"); else note "Could not remove $p"; fi
  else
    ABSENT+=("$2")
  fi
}

# ---------- steps ----------

stop_usb_pieces() {
  if command -v systemctl >/dev/null 2>&1 && [ -e "$UNIT_FILE" ]; then
    run systemctl stop athena-usb-backup.service 2>/dev/null || true
  fi
  if mountpoint -q "$USB_MNT" 2>/dev/null; then
    run umount "$USB_MNT" || note "Could not unmount $USB_MNT; unplug the drive after the uninstall finishes."
  fi
}

remove_containers() {
  command -v docker >/dev/null 2>&1 || { ABSENT+=("Docker containers (Docker is not installed)"); return 0; }
  local project; project="$(basename "$INSTALL_DIR")"
  if [ -f "$INSTALL_DIR/docker-compose.yml" ]; then
    say "Stopping Athena and deleting its containers, database volume and certificate volume..."
    if [ "$DRY_RUN" = 1 ]; then
      printf '[dry run] (cd %s && docker compose --profile tools down -v --remove-orphans --rmi local)\n' "$INSTALL_DIR"
    else
      ( cd "$INSTALL_DIR" && docker compose --profile tools down -v --remove-orphans --rmi local ) \
        || note "Docker reported a problem while removing Athena's containers. Check with: docker ps -a"
    fi
    REMOVED+=("Athena containers, database and certificate volumes, and Athena's built images")
  else
    # Partly installed: find leftovers by Docker's own project label.
    local -a ids=() vols=()
    mapfile -t ids  < <(docker ps -aq --filter "label=com.docker.compose.project=$project" 2>/dev/null || true)
    mapfile -t vols < <(docker volume ls -q --filter "label=com.docker.compose.project=$project" 2>/dev/null || true)
    if [ "${#ids[@]}" -gt 0 ];  then run docker rm -f "${ids[@]}"      >/dev/null; REMOVED+=("leftover Athena containers"); fi
    if [ "${#vols[@]}" -gt 0 ]; then run docker volume rm "${vols[@]}" >/dev/null; REMOVED+=("leftover Athena volumes"); fi
    [ "${#ids[@]}" -gt 0 ] || [ "${#vols[@]}" -gt 0 ] || ABSENT+=("Athena containers and volumes")
  fi
}

remove_files() {
  if is_safe_install_dir "$INSTALL_DIR"; then
    remove_path "$INSTALL_DIR" "Athena program folder ($INSTALL_DIR, including the .env file)"
  elif [ -e "$INSTALL_DIR" ]; then
    note "Left $INSTALL_DIR alone: it does not look like an Athena install folder."
  else
    ABSENT+=("Athena program folder")
  fi
  remove_path "$CRON_FILE"       "nightly clean-up and backup schedule"
  remove_path "$LOGROTATE_FILE"  "log rotation settings"
  remove_path "$BIN_ATHENA"      "the 'athena' command"
  remove_path "$SBIN_BACKUP"     "the backup program"
  remove_path "$LIB_DIR"         "backup program libraries"
  remove_path "$UDEV_RULE"       "USB plug-in rule"
  remove_path "$UNIT_FILE"       "USB plug-in service"
  remove_path "$CONF_DIR"        "backup key (public half) and USB drive list"
  remove_path "$STATE_DIR"       "backup status file"
  local f
  for f in athena-install.log athena-purge.log athena-backup.log; do
    remove_path "$LOG_GLOB_DIR/$f" "log file $f"
  done
  if command -v systemctl >/dev/null 2>&1; then run systemctl daemon-reload || true; fi
  if command -v udevadm   >/dev/null 2>&1; then run udevadm control --reload || true; fi
}

remove_backups() {
  if [ "$DELETE_BACKUPS" = 1 ]; then
    remove_path "$BACKUP_DIR" "backups stored on this server ($BACKUP_DIR)"
  elif [ -d "$BACKUP_DIR" ]; then
    KEPT_BACKUPS=1
  fi
}

remove_firewall() {
  [ "$REMOVE_FIREWALL" = 1 ] || return 0
  command -v ufw >/dev/null 2>&1 || { note "ufw is not installed; no firewall rules to remove."; return 0; }
  local n nums
  nums="$(ufw status numbered 2>/dev/null | athena_ufw_rule_numbers || true)"
  if [ -z "$nums" ]; then ABSENT+=("firewall rules for ports 80 and 443"); return 0; fi
  for n in $nums; do run ufw --force delete "$n" >/dev/null; done
  REMOVED+=("firewall rules for web access (ports 80 and 443)")
}

# ---------- main ----------

show_plan() {
  say ""
  say "This will REMOVE from this server:"
  say "  - Athena and everything in its database (all clients, appointments, calls, users)"
  say "  - the saved certificate authority (staff computers will need the NEW certificate after a reinstall)"
  say "  - the .env file with the database password and encryption key"
  say "  - the 'athena' command, nightly schedule, USB plug-in rule, logs, and backup key settings"
  say ""
  say "It will NOT touch: your USB backup drive, your saved private backup key, the folder you cloned"
  say "Athena into, or Docker itself."
  if [ "$DELETE_BACKUPS" = 1 ]; then say "It WILL also delete the backups stored on this server ($BACKUP_DIR)."
  else say "Backups stored on this server ($BACKUP_DIR) will be KEPT."; fi
  if [ "$REMOVE_FIREWALL" = 1 ]; then say "It WILL also remove the firewall rules for web access (ports 80 and 443)."
  else say "Firewall rules will be left as they are."; fi
  say ""
}

main() {
  local arg
  for arg in "$@"; do
    case "$arg" in
      --dry-run) DRY_RUN=1 ;;
      --yes) ASSUME_YES=1 ;;
      --delete-backups) DELETE_BACKUPS=1 ;;
      --remove-firewall-rules) REMOVE_FIREWALL=1 ;;
      -h|--help) usage; exit 0 ;;
      *) say "Unknown option: $arg"; usage; exit 1 ;;
    esac
  done
  [ "$(id -u)" -eq 0 ] || { say "Please run this with sudo:  sudo ./uninstall.sh"; exit 1; }

  # If we are running from inside the folder we are about to delete, continue from a temporary copy.
  local self; self="$(readlink -f "${BASH_SOURCE[0]}")"
  if [[ "$self" == "$INSTALL_DIR"/* ]] && [ -z "${ATHENA_UNINSTALL_RELOCATED:-}" ]; then
    local tmp; tmp="$(mktemp -d)"; cp "$self" "$tmp/uninstall.sh"
    ATHENA_UNINSTALL_RELOCATED=1 exec bash "$tmp/uninstall.sh" "$@"
  fi

  say ""
  say "  Project Athena - uninstaller"
  [ "$DRY_RUN" = 1 ] && say "  (DRY RUN: nothing will be changed)"
  show_plan

  if [ "$ASSUME_YES" != 1 ] && [ "$DRY_RUN" != 1 ]; then
    if [ -d "$BACKUP_DIR" ] && [ "$DELETE_BACKUPS" != 1 ]; then
      local a; read -r -p "Also delete the backups stored on this server? [y/N]: " a </dev/tty || a=""
      case "$a" in [Yy]*) DELETE_BACKUPS=1; say "  -> backups will be deleted too." ;; esac
    fi
    if [ "$REMOVE_FIREWALL" != 1 ] && command -v ufw >/dev/null 2>&1; then
      local b; read -r -p "Also remove the firewall rules for web access (ports 80, 443)? [y/N]: " b </dev/tty || b=""
      case "$b" in [Yy]*) REMOVE_FIREWALL=1; say "  -> firewall rules will be removed too." ;; esac
    fi
    local typed
    read -r -p "To go ahead, type DELETE ATHENA: " typed </dev/tty || typed=""
    [ "$typed" = "DELETE ATHENA" ] || { say "Cancelled. Nothing was changed."; exit 1; }
  fi

  stop_usb_pieces
  remove_containers
  remove_files
  remove_backups
  remove_firewall

  say ""
  say "Finished$([ "$DRY_RUN" = 1 ] && echo ' (dry run: nothing was actually changed)')."
  local r
  if [ "${#REMOVED[@]}" -gt 0 ]; then say "Removed:"; for r in "${REMOVED[@]}"; do say "  - $r"; done; fi
  if [ "${#ABSENT[@]}" -gt 0 ];  then say "Already gone / not found:"; for r in "${ABSENT[@]}"; do say "  - $r"; done; fi
  say ""
  [ -n "${KEPT_BACKUPS:-}" ] && say "Kept: the backups in $BACKUP_DIR (delete them yourself with: sudo rm -rf $BACKUP_DIR)."
  say "Reminders:"
  say "  - Remove the old Athena certificate from staff computers (a reinstall creates a new one)."
  say "  - Your USB backup drive and your saved private backup key were not touched."
  say "  - Docker and the helper packages (age, ufw, ...) are still installed; they may be used by other things."
  say "  - Free disk space from unused images with:  sudo docker image prune -a"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi