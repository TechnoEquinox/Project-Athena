# shellcheck shell=bash
# Installer step: set up encrypted backups. Needs ui.sh. Run from the repository root.

: "${LIB_DEST:=/usr/local/lib/athena}"
: "${SBIN_DEST:=/usr/local/sbin}"
: "${CONF_DIR:=/etc/athena}"
: "${BACKUP_DIR:=/var/backups/athena}"
: "${STATE_DIR:=/var/lib/athena}"

# Make a key pair. Only the PUBLIC key stays on the server; the person installing must save the private one.
setup_backup_key() {
  if [ -s "$CONF_DIR/backup.pub" ]; then
    ok "A backup key already exists - keeping it."
    return 0
  fi
  local tmpdir tmp secret pub tail6 answer tries=0
  tmpdir="$(mktemp -d)"; tmp="$tmpdir/key.txt"   # age-keygen will not overwrite an existing file
  age-keygen -o "$tmp" >/dev/null 2>&1 || { rm -rf "$tmpdir"; die "Could not create the backup key."; }
  secret="$(grep '^AGE-SECRET-KEY-' "$tmp")"
  pub="$(age-keygen -y "$tmp")"
  shred -u "$tmp" 2>/dev/null || rm -f "$tmp"
  rmdir "$tmpdir" 2>/dev/null || true
  tail6="${secret: -6}"

  # Printed directly (not through say) so the secret never reaches the install log.
  printf '\n%s' "$C_BOLD"
  printf '  ============================================================\n'
  printf '   YOUR BACKUP KEY - save this now, it is shown only once\n'
  printf '  ============================================================\n%s\n' "$C_OFF"
  printf '   %s\n\n' "$secret"
  cat <<'WHY'
   Every backup is locked with this key so that a lost USB stick or
   stolen server reveals nothing. This server keeps only the lock, NOT
   the key. If you lose this key, your backups can never be opened.

   Save it in TWO places: a password manager, and a printed copy in a
   locked drawer (together with your .env file copy).
WHY
  if [ "${ATHENA_YES:-0}" = "1" ]; then
    warn "Unattended mode: the key was not confirmed. Save it from the screen above."
  else
    while :; do
      answer="$(ask "To confirm you saved it, type the LAST 6 characters of the key" "")"
      [ "$answer" = "$tail6" ] && break
      tries=$((tries + 1))
      [ "$tries" -lt 5 ] || die "Key not confirmed, so nothing was changed. Run the installer again to get a new key."
      warn "That does not match. Check the saved copy and try again."
    done
  fi
  mkdir -p "$CONF_DIR"
  printf '%s\n' "$pub" >"$CONF_DIR/backup.pub"
  chmod 644 "$CONF_DIR/backup.pub"
  ok "Backup key created. The server holds only the public half."
}

setup_backups() {
  install -d -m 755 "$CONF_DIR" "$LIB_DEST" "$STATE_DIR" "$SBIN_DEST"
  install -d -m 700 "$BACKUP_DIR"
  install -m 644 installer/lib/backup.sh "$LIB_DEST/backup.sh"
  install -m 755 installer/files/athena-backup "$SBIN_DEST/athena-backup"
  setup_backup_key
  if [ "${SKIP_FIRST_BACKUP:-0}" = "1" ]; then return 0; fi
  say "Making the first backup now to prove it works..."
  if ATHENA_DIR="${INSTALL_DIR:-/opt/athena}" "$SBIN_DEST/athena-backup" >>/var/log/athena-backup.log 2>&1; then
    ok "First backup created in $BACKUP_DIR (encrypted)."
  else
    die "The first backup failed. See /var/log/athena-backup.log, fix the problem, and run the installer again."
  fi
}