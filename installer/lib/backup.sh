# shellcheck shell=bash
# shellcheck disable=SC2012,SC2016
# Athena backup and restore engine. Installed to /usr/local/lib/athena/backup.sh.
# Every docker call is a tiny function (db_dump, db_check_dump, ...) so tests can replace them.

: "${ATHENA_DIR:=/opt/athena}"
: "${BACKUP_DIR:=/var/backups/athena}"
: "${STATE_DIR:=/var/lib/athena}"
: "${CONF_DIR:=/etc/athena}"
: "${KEEP_DAILY:=14}"
: "${KEEP_MONTHLY:=12}"

blog() { printf '%s %s\n' "$(date '+%F %T')" "$*"; }

# ---------- names and retention (pure) ----------

backup_filename() { printf 'athena-backup-%s.tar.age' "$(date -u +%Y%m%d-%H%M%S)"; }

is_backup_name() { [[ "${1:-}" =~ ^athena-backup-[0-9]{8}-[0-9]{6}\.tar\.age$ ]]; }

# stdin: file names. stdout: the ones to KEEP = newest DAILY, plus the latest backup of each of the newest MONTHLY months.
select_keep() {
  local daily="${1:-$KEEP_DAILY}" monthly="${2:-$KEEP_MONTHLY}"
  grep -E '^athena-backup-[0-9]{8}-[0-9]{6}\.tar\.age$' | sort -r | awk -v d="$daily" -v m="$monthly" '
    { ym = substr($0, 15, 6)
      if (NR <= d) print
      else if (!(ym in seen) && months < m) { print }
      if (!(ym in seen)) { seen[ym] = 1; months++ } }
  '
}

apply_retention() {
  local dir="${1:-$BACKUP_DIR}" f keep
  keep="$(cd "$dir" && ls -1 | select_keep)"
  while IFS= read -r f; do
    is_backup_name "$f" || continue
    if ! grep -qxF "$f" <<<"$keep"; then
      rm -f "$dir/$f" "$dir/$f.sha256"
      blog "Removed old backup $f"
    fi
  done < <(cd "$dir" && ls -1)
}

# ---------- status file (read by the admin page later) ----------

# write_status ok(true|false) message [file] [bytes]
write_status() {
  mkdir -p "$STATE_DIR"
  python3 - "$STATE_DIR/backup-status.json" "$BACKUP_DIR" "$@" <<'PY'
import json, os, sys, time
path, bdir, ok, message = sys.argv[1], sys.argv[2], sys.argv[3] == "true", sys.argv[4]
fname = sys.argv[5] if len(sys.argv) > 5 else ""
size = int(sys.argv[6]) if len(sys.argv) > 6 and sys.argv[6] else 0
try:
    with open(path) as fh:
        st = json.load(fh)
except Exception:
    st = {}
now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
st.update({"last_attempt": now, "ok": ok, "message": message})
if ok:
    st.update({"last_success": now, "last_file": fname, "last_bytes": size})
st["count"] = len([n for n in os.listdir(bdir) if n.startswith("athena-backup-") and n.endswith(".tar.age")]) if os.path.isdir(bdir) else 0
tmp = path + ".tmp"
with open(tmp, "w") as fh:
    json.dump(st, fh, indent=2)
os.chmod(tmp, 0o644)
os.replace(tmp, path)
PY
}

# ---------- things that talk to Docker (replaceable in tests) ----------

dc() { ( cd "$ATHENA_DIR" && docker compose "$@" ); }

db_dump()       { dc exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >"$1"; }
db_check_dump() { dc exec -T db pg_restore --list <"$1" >/dev/null; }
db_revision()   { dc exec -T db sh -c 'psql -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select version_num from alembic_version"' 2>/dev/null | head -1; }
ca_export()     { mkdir -p "$1" && dc cp caddy:/data/caddy/pki "$1"; }
db_restore()    { dc exec -T db sh -c 'pg_restore --clean --if-exists --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <"$1"; }
db_sql()        { dc exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v admin_user="$POSTGRES_USER" -v app_pw="$1" -v admin_pw="$2"' sh "$@"; }
ca_import()     { dc cp "$1" caddy:/data/caddy/; }

# ---------- the backup ----------

_do_backup() {
  local stage name partial final bytes
  [ -s "$CONF_DIR/backup.pub" ] || { BACKUP_ERR="No backup key is set up ($CONF_DIR/backup.pub is missing)."; return 1; }
  [ -s "$ATHENA_DIR/.env" ]     || { BACKUP_ERR="Cannot find $ATHENA_DIR/.env."; return 1; }
  umask 077
  mkdir -p "$BACKUP_DIR"; chmod 700 "$BACKUP_DIR"
  stage="$(mktemp -d "$BACKUP_DIR/.stage.XXXXXX")"
  # shellcheck disable=SC2064
  trap "rm -rf '$stage'" RETURN

  db_dump "$stage/database.dump" || { BACKUP_ERR="The database dump failed (is the database running?)."; return 1; }
  [ -s "$stage/database.dump" ]  || { BACKUP_ERR="The database dump was empty."; return 1; }
  db_check_dump "$stage/database.dump" || { BACKUP_ERR="The database dump could not be read back, so it was not saved."; return 1; }

  cp "$ATHENA_DIR/.env" "$stage/athena.env"
  local ca=false
  if ca_export "$stage/caddy" >/dev/null 2>&1 && [ -d "$stage/caddy/pki" ]; then ca=true; fi

  python3 - "$stage/manifest.json" "$(cat "$ATHENA_DIR/VERSION" 2>/dev/null || echo unknown)" "$(db_revision || true)" "$ca" <<'PY'
import json, socket, sys, time
json.dump({"created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "athena_version": sys.argv[2],
           "database_revision": sys.argv[3], "host": socket.gethostname(), "includes_certificate_authority": sys.argv[4] == "true",
           "contents": ["database.dump", "athena.env", "caddy/pki (if present)", "manifest.json"]},
          open(sys.argv[1], "w"), indent=2)
PY

  name="$(backup_filename)"; partial="$BACKUP_DIR/.$name.partial"; final="$BACKUP_DIR/$name"
  if ! tar -C "$stage" -cf - . | age -R "$CONF_DIR/backup.pub" -o "$partial"; then
    rm -f "$partial"; BACKUP_ERR="Encrypting the backup failed."; return 1
  fi
  [ -s "$partial" ] && [ "$(head -c 21 "$partial")" = "age-encryption.org/v1" ] \
    || { rm -f "$partial"; BACKUP_ERR="The encrypted file looks wrong, so it was discarded."; return 1; }
  mv "$partial" "$final"
  ( cd "$BACKUP_DIR" && sha256sum "$name" >"$name.sha256" )
  bytes="$(stat -c %s "$final")"
  apply_retention "$BACKUP_DIR"
  BACKUP_FILE="$name"; BACKUP_BYTES="$bytes"; BACKUP_CA="$ca"
}

run_backup() {
  BACKUP_ERR="Unknown error."; BACKUP_FILE=""; BACKUP_BYTES=0; BACKUP_CA=true
  if _do_backup; then
    local note="Backup saved."
    [ "$BACKUP_CA" = true ] || note="Backup saved, but the certificate files could not be included."
    write_status true "$note" "$BACKUP_FILE" "$BACKUP_BYTES"
    blog "OK $BACKUP_FILE ($BACKUP_BYTES bytes). $note"
    return 0
  fi
  write_status false "$BACKUP_ERR"
  blog "FAILED: $BACKUP_ERR"
  return 1
}

# ---------- the restore ----------

# restore_backup BACKUPFILE KEYFILE
restore_backup() {
  local file="$1" key="$2" tmp ts
  [ -r "$file" ] || { echo "Cannot read backup file: $file" >&2; return 1; }
  [ -r "$key" ]  || { echo "Cannot read key file: $key" >&2; return 1; }
  umask 077
  mkdir -p "$BACKUP_DIR"; chmod 700 "$BACKUP_DIR"
  tmp="$(mktemp -d "$BACKUP_DIR/.restore.XXXXXX")"
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp'" RETURN
  if ! age -d -i "$key" "$file" | tar -x --no-same-owner -C "$tmp"; then
    echo "Could not open the backup. Is this the right key file, and is the backup complete?" >&2; return 1
  fi
  [ -s "$tmp/database.dump" ] && [ -s "$tmp/athena.env" ] || { echo "This does not look like an Athena backup." >&2; return 1; }
  echo "Backup contents:"; cat "$tmp/manifest.json" 2>/dev/null || true
  echo
  if [ "${ATHENA_YES:-0}" != 1 ]; then
    echo "This REPLACES everything currently in Athena (clients, appointments, calls, users) with the backup."
    read -r -p "Type RESTORE to continue: " reply </dev/tty || reply=""
    [ "$reply" = "RESTORE" ] || { echo "Cancelled. Nothing was changed."; return 1; }
  fi
  ts="$(date +%Y%m%d-%H%M%S)"
  dc stop api caddy >/dev/null 2>&1 || true
  [ -e "$ATHENA_DIR/.env" ] && cp -p "$ATHENA_DIR/.env" "$ATHENA_DIR/.env.before-restore-$ts"
  cp "$tmp/athena.env" "$ATHENA_DIR/.env"; chmod 600 "$ATHENA_DIR/.env"
  db_restore "$tmp/database.dump" || { echo "The database restore failed. Your previous .env is saved as .env.before-restore-$ts" >&2; return 1; }
  # The restored .env has the passwords the backup was made with; make the database agree with them.
  local app_pw admin_pw
  app_pw="$(grep -m1 '^APP_DB_PASSWORD=' "$ATHENA_DIR/.env" | cut -d= -f2-)"
  admin_pw="$(grep -m1 '^POSTGRES_PASSWORD=' "$ATHENA_DIR/.env" | cut -d= -f2-)"
  printf "ALTER ROLE athena_app PASSWORD :'app_pw';\nALTER ROLE :\"admin_user\" PASSWORD :'admin_pw';\n" | db_sql "$app_pw" "$admin_pw"
  [ -d "$tmp/caddy/pki" ] && ca_import "$tmp/caddy/pki"
  dc up -d >/dev/null
  echo "Restore finished. Athena is starting. Check it with:  athena status"
}