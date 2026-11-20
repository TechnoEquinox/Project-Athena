#!/usr/bin/env bash
# shellcheck disable=SC2015
# Tests for uninstall.sh using a pretend filesystem and fake docker/ufw/systemctl commands.
#   bash installer/tests/uninstall_test.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT
pass=0; fail=0
t() { local n="$1"; shift; if "$@"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $n"; fi; }
no() { ! "$@"; }

# ---- fake commands that only record what they were asked to do ----
SHIM="$D/shim"; mkdir -p "$SHIM"; : >"$D/calls.log"
for c in docker systemctl udevadm umount; do
  printf '#!/bin/sh\necho "%s $*" >>"%s/calls.log"\nexit 0\n' "$c" "$D" >"$SHIM/$c"
done
cat >"$SHIM/ufw" <<SH
#!/bin/sh
if [ "\$1" = status ]; then
cat <<'S'
Status: active

     To                         Action      From
     --                         ------      ----
[ 1] 22/tcp                     LIMIT IN    192.168.1.0/24
[ 2] 80,443/tcp                 ALLOW IN    192.168.1.0/24
[ 3] 443/udp                    ALLOW IN    192.168.1.0/24
[ 4] 80,443/tcp (v6)            ALLOW IN    Anywhere (v6)
[ 5] 8080/tcp                   ALLOW IN    Anywhere
S
else echo "ufw \$*" >>"$D/calls.log"; fi
SH
chmod +x "$SHIM"/*
export PATH="$SHIM:$PATH"

build_world() {  # creates a fake installed system under $D/w
  rm -rf "$D/w"; mkdir -p "$D/w"/{opt/athena/installer,etc/cron.d,etc/logrotate.d,usr/local/bin,usr/local/sbin,usr/local/lib/athena,etc/udev/rules.d,etc/systemd/system,etc/athena,var/lib/athena,var/backups/athena,var/log,run}
  W="$D/w"
  touch "$W/opt/athena/docker-compose.yml" "$W/opt/athena/.env" "$W/etc/cron.d/athena" "$W/etc/logrotate.d/athena" \
        "$W/usr/local/bin/athena" "$W/usr/local/sbin/athena-backup" "$W/usr/local/lib/athena/backup.sh" \
        "$W/etc/udev/rules.d/99-athena-backup.rules" "$W/etc/systemd/system/athena-usb-backup.service" \
        "$W/etc/athena/backup.pub" "$W/var/lib/athena/backup-status.json" "$W/var/backups/athena/athena-backup-1.tar.age" \
        "$W/var/log/athena-install.log" "$W/var/log/athena-purge.log" "$W/var/log/athena-backup.log" "$W/var/log/syslog"
  echo 0.2 >"$W/opt/athena/VERSION"
  : >"$D/calls.log"
  export ATHENA_DIR="$W/opt/athena" CRON_FILE="$W/etc/cron.d/athena" LOGROTATE_FILE="$W/etc/logrotate.d/athena" BIN_ATHENA="$W/usr/local/bin/athena" \
         SBIN_BACKUP="$W/usr/local/sbin/athena-backup" LIB_DIR="$W/usr/local/lib/athena" UDEV_RULE="$W/etc/udev/rules.d/99-athena-backup.rules" \
         UNIT_FILE="$W/etc/systemd/system/athena-usb-backup.service" CONF_DIR="$W/etc/athena" STATE_DIR="$W/var/lib/athena" \
         BACKUP_DIR="$W/var/backups/athena" USB_MNT="$W/run/athena-usb" LOG_GLOB_DIR="$W/var/log"
}
U() {
  # Safety: a test must never point at a real install.
  case "${ATHENA_DIR:-}" in "$D"/*|/) ;; *) echo "test bug: ATHENA_DIR is not a test folder"; exit 99 ;; esac
  bash "$ROOT/uninstall.sh" "$@" >"$D/out.txt" 2>&1; }

# ---- pure functions ----
. "$ROOT/uninstall.sh"
t safe_good        bash -c ". '$ROOT/uninstall.sh'; build() { :; }; mkdir -p '$D/ok/a/installer'; touch '$D/ok/a/docker-compose.yml' '$D/ok/a/VERSION'; is_safe_install_dir '$D/ok/a'"
for bad in "" "/" "/opt" "/usr/local" "/etc" "relative/path" "$D"; do
  t "unsafe '$bad'" no is_safe_install_dir "$bad"
done
t unsafe_no_marker no is_safe_install_dir "$D/shim"
t ufw_numbers test "$(ufw status numbered | athena_ufw_rule_numbers | tr '\n' ' ')" = "4 3 2 "

# ---- dry run changes nothing ----
build_world
t dry_run_ok        U --dry-run --delete-backups --remove-firewall-rules
t dry_run_mentions  grep -q "dry run" "$D/out.txt"
t dry_keeps_dir     test -d "$W/opt/athena"
t dry_keeps_cron    test -f "$W/etc/cron.d/athena"
t dry_keeps_backups test -d "$W/var/backups/athena"
t dry_no_docker     no grep -q '^docker' "$D/calls.log"

# ---- without confirmation it refuses ----
build_world
# setsid removes the terminal, so the confirmation prompt cannot be answered and must cancel
t no_tty_cancels    no setsid -w bash "$ROOT/uninstall.sh" </dev/null
t refused_keeps     test -d "$W/opt/athena"

# ---- real run keeps backups and firewall by default ----
build_world
t run_ok            U --yes
t dir_gone          test ! -e "$W/opt/athena"
t cron_gone         test ! -e "$W/etc/cron.d/athena"
t logrotate_gone    test ! -e "$W/etc/logrotate.d/athena"
t cmd_gone          test ! -e "$W/usr/local/bin/athena"
t backup_prog_gone  test ! -e "$W/usr/local/sbin/athena-backup"
t lib_gone          test ! -e "$W/usr/local/lib/athena"
t udev_gone         test ! -e "$W/etc/udev/rules.d/99-athena-backup.rules"
t unit_gone         test ! -e "$W/etc/systemd/system/athena-usb-backup.service"
t conf_gone         test ! -e "$W/etc/athena"
t state_gone        test ! -e "$W/var/lib/athena"
t logs_gone         test ! -e "$W/var/log/athena-install.log" -a ! -e "$W/var/log/athena-backup.log"
t other_logs_kept   test -f "$W/var/log/syslog"
t backups_kept      test -f "$W/var/backups/athena/athena-backup-1.tar.age"
t says_kept         grep -q "Kept: the backups" "$D/out.txt"
t docker_down       grep -q 'docker compose --profile tools down -v --remove-orphans --rmi local\|docker compose' "$D/calls.log"
t firewall_untouched no grep -q '^ufw' "$D/calls.log"
t reloaded          grep -q 'udevadm control --reload' "$D/calls.log"

# ---- running it again on an already-clean system is fine ----
: >"$D/calls.log"
t second_run_ok     U --yes
t second_run_says   grep -q "Already gone" "$D/out.txt"

# ---- optional deletions ----
build_world
t full_run_ok       U --yes --delete-backups --remove-firewall-rules
t backups_deleted   test ! -e "$W/var/backups/athena"
t fw_deleted_4_3_2  test "$(grep '^ufw --force delete' "$D/calls.log" | awk '{print $4}' | tr '\n' ' ')" = "4 3 2 "
t fw_kept_ssh       no grep -q 'delete 1$\|delete 5$' "$D/calls.log"

# ---- never deletes a folder that is not an Athena install ----
build_world; rm "$W/opt/athena/VERSION"
t wrong_dir_ok      U --yes
t wrong_dir_kept    test -d "$W/opt/athena"
t wrong_dir_says    grep -q "does not look like an Athena" "$D/out.txt"
build_world; export ATHENA_DIR="/"
t slash_ok          U --yes
t slash_survives    test -d "/etc" -a -d "$W/etc/cron.d"

# ---- leftovers when the program folder is already gone ----
build_world; rm -rf "$W/opt/athena"
t partial_ok        U --yes
t partial_cleaned   test ! -e "$W/etc/cron.d/athena"

# ---- bad option ----
t bad_option        no U --nonsense

echo "passed: $pass  failed: $fail"; [ "$fail" -eq 0 ]