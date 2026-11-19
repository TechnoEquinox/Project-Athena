# shellcheck shell=bash
# shellcheck disable=SC2016,SC2012
# USB backup drives. Installed to /usr/local/lib/athena/usb.sh. Needs backup.sh loaded first.
#
# A drive is only used if (1) its filesystem label is ATHENA-BACKUP and (2) its UUID is in
# /etc/athena/usb-drives, which only 'athena usb-setup' writes. Anything else is ignored.

: "${USB_LABEL:=ATHENA-BACKUP}"
: "${USB_CONF:=$CONF_DIR/usb-drives}"
: "${USB_MNT:=/run/athena-usb}"
: "${USB_STALE_DAYS:=7}"

usb_known_uuid() { [ -n "${1:-}" ] && grep -qxF "$1" "$USB_CONF" 2>/dev/null; }

# ---------- talking to the system (replaceable in tests) ----------

usb_lsblk_json() { lsblk -J -p -o PATH,TYPE,TRAN,SIZE,MODEL,VENDOR,UUID,LABEL,FSTYPE,MOUNTPOINTS 2>/dev/null; }
usb_mount()      { mkdir -p "$USB_MNT" && mount -o nodev,nosuid,noexec "$1" "$USB_MNT"; }
usb_umount()     { sync; umount "$USB_MNT"; }

# Connected drives we set up: prints "DEVICE UUID" per line
usb_find_drives() {
  usb_lsblk_json | python3 -c '
import json, sys
label, conf = sys.argv[1], sys.argv[2]
try: known = set(open(conf).read().split())
except OSError: known = set()
def walk(nodes):
    for n in nodes:
        yield n
        yield from walk(n.get("children") or [])
for n in walk(json.load(sys.stdin).get("blockdevices", [])):
    if n.get("label") == label and n.get("fstype") == "ext4" and n.get("uuid") in known:
        print(n["path"], n["uuid"])
' "$USB_LABEL" "$USB_CONF"
}

# Whole USB disks that are safe to offer for erasing: prints "PATH|SIZE|DESCRIPTION|EXISTING"
usb_candidates() {
  usb_lsblk_json | python3 -c '
import json, sys
def mounts(n):
    out = [m for m in (n.get("mountpoints") or []) if m]
    for c in n.get("children") or []: out += mounts(c)
    return out
for n in json.load(sys.stdin).get("blockdevices", []):
    if n.get("type") != "disk" or n.get("tran") != "usb": continue
    if mounts(n): continue
    desc = " ".join(x.strip() for x in (n.get("vendor"), n.get("model")) if x and x.strip()) or "USB drive"
    kids = [c.get("label") or c.get("fstype") or "unknown" for c in (n.get("children") or [])]
    print("%s|%s|%s|%s" % (n["path"], n.get("size") or "?", desc, ", ".join(kids) or "empty"))
'
}

# ---------- USB status inside backup-status.json ----------

# write_usb_status ok(true|false|none) present(true|false) message
write_usb_status() {
  mkdir -p "$STATE_DIR"
  python3 - "$STATE_DIR/backup-status.json" "$@" <<'PY'
import json, os, sys, time
path, ok, present, message = sys.argv[1], sys.argv[2], sys.argv[3] == "true", sys.argv[4]
try:
    st = json.load(open(path))
except Exception:
    st = {}
now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
st.update({"usb_present": present, "usb_message": message})
if ok != "none":
    st.update({"usb_last_attempt": now, "usb_ok": ok == "true"})
    if ok == "true":
        st["usb_last_success"] = now
tmp = path + ".tmp"
json.dump(st, open(tmp, "w"), indent=2)
os.chmod(tmp, 0o644)
os.replace(tmp, path)
PY
}

# ---------- copying ----------

# Copy every backup the drive does not have yet. Sets USB_ERR on failure. Drive must be mounted.
usb_copy_backups() {
  local dest="$USB_MNT/athena-backups" f expected actual
  mkdir -p "$dest"
  while IFS= read -r f; do
    is_backup_name "$f" || continue
    if [ -f "$dest/$f" ] && [ "$(stat -c %s "$dest/$f")" = "$(stat -c %s "$BACKUP_DIR/$f")" ]; then continue; fi
    if ! cp "$BACKUP_DIR/$f" "$dest/.$f.partial" 2>/dev/null; then
      rm -f "$dest/.$f.partial"; USB_ERR="Copying to the drive failed (is it full or damaged?)."; return 1
    fi
    expected="$(cut -d' ' -f1 "$BACKUP_DIR/$f.sha256" 2>/dev/null)"
    actual="$(sha256sum "$dest/.$f.partial" | cut -d' ' -f1)"
    if [ -z "$expected" ] || [ "$expected" != "$actual" ]; then
      rm -f "$dest/.$f.partial"; USB_ERR="A copy on the drive did not match the original, so it was discarded."; return 1
    fi
    mv "$dest/.$f.partial" "$dest/$f"
    cp "$BACKUP_DIR/$f.sha256" "$dest/$f.sha256" 2>/dev/null || true
  done < <(cd "$BACKUP_DIR" && ls -1 | sort -r)
  apply_retention "$dest"
}

# usb_sync_one DEVICE UUID
usb_sync_one() {
  USB_ERR=""
  if ! usb_mount "$1"; then USB_ERR="The drive could not be mounted."; return 1; fi
  local rc=0
  usb_copy_backups || rc=1
  sync
  if ! usb_umount; then
    [ "$rc" -eq 0 ] && USB_ERR="Copied, but the drive could not be unmounted; wait a minute and run 'athena backup' again before removing it."
    return 1
  fi
  return "$rc"
}

# Copy to every connected drive that we set up. A missing drive is normal, not an error.
usb_sync_all() {
  local drives dev uuid fails=0 copied=0
  drives="$(usb_find_drives)"
  if [ -z "$drives" ]; then
    write_usb_status none false "No backup drive connected."
    blog "USB: no backup drive connected."
    return 0
  fi
  while read -r dev uuid; do
    [ -n "$dev" ] || continue
    if usb_sync_one "$dev" "$uuid"; then
      copied=$((copied + 1)); blog "USB: copied to $dev ($uuid)."
    else
      fails=$((fails + 1)); blog "USB FAILED on $dev: $USB_ERR"
      write_usb_status false true "$USB_ERR"
    fi
  done <<<"$drives"
  if [ "$fails" -eq 0 ]; then
    write_usb_status true true "Backups copied to the USB drive. It is safe to remove."
  fi
  [ "$fails" -eq 0 ]
}

# ---------- one-time drive preparation ----------

# Make one partition covering the disk; prints its path. (Replaceable in tests.)
usb_make_partition() {
  local dev="$1" part
  printf 'label: gpt\n,,L\n' | sfdisk --quiet "$dev" || return 1
  command -v partprobe >/dev/null && partprobe "$dev" 2>/dev/null
  command -v udevadm   >/dev/null && udevadm settle 2>/dev/null
  sleep 1
  part="$(lsblk -nrpo PATH,TYPE "$dev" | awk '$2=="part" {print $1; exit}')"
  [ -b "$part" ] || return 1
  printf '%s\n' "$part"
}

# usb_format_drive DEVICE : erases it, formats ext4, and remembers its UUID. DESTRUCTIVE.
usb_format_drive() {
  local dev="$1" part uuid
  wipefs -a "$dev" >/dev/null 2>&1 || { echo "Could not clear the drive." >&2; return 1; }
  part="$(usb_make_partition "$dev")" || { echo "Could not create a partition." >&2; return 1; }
  mkfs.ext4 -q -F -L "$USB_LABEL" -m 0 "$part" || { echo "Could not format the drive." >&2; return 1; }
  uuid="$(blkid -s UUID -o value "$part")"
  [ -n "$uuid" ] || { echo "Could not read the new drive's ID." >&2; return 1; }
  mkdir -p "$CONF_DIR"; touch "$USB_CONF"; chmod 644 "$USB_CONF"
  grep -qxF "$uuid" "$USB_CONF" || printf '%s\n' "$uuid" >>"$USB_CONF"
  usb_mount "$part" || { echo "Could not mount the new drive." >&2; return 1; }
  mkdir -p "$USB_MNT/athena-backups"
  printf 'This drive holds encrypted Project Athena backups.\nThey can only be opened with the backup key kept by your administrator.\nSee: athena restore\n' >"$USB_MNT/README-ATHENA-BACKUPS.txt"
  usb_umount
  USB_NEW_UUID="$uuid"
}

usb_setup() {
  local cands=() line n=0 choice dev size desc existing typed
  mapfile -t cands < <(usb_candidates)
  if [ "${#cands[@]}" -eq 0 ]; then
    echo "No USB drive found."
    echo "Plug the drive into the server, wait 5 seconds, and run this again."
    echo "(Drives that are already in use are hidden on purpose.)"
    return 1
  fi
  echo "USB drives found:"
  for line in "${cands[@]}"; do
    n=$((n + 1)); IFS='|' read -r dev size desc existing <<<"$line"
    printf '  %d) %s   %s   %s   [now contains: %s]\n' "$n" "$dev" "$size" "$desc" "$existing"
  done
  read -r -p "Which drive number? " choice </dev/tty || choice=""
  if ! [[ "$choice" =~ ^[0-9]+$ ]] || [ "$choice" -lt 1 ] || [ "$choice" -gt "${#cands[@]}" ]; then
    echo "Cancelled. Nothing was changed."; return 1
  fi
  IFS='|' read -r dev size desc existing <<<"${cands[$((choice - 1))]}"
  echo
  echo "This will ERASE $dev ($size, $desc). Everything on it will be lost."
  read -r -p "To confirm, type the device name exactly ($dev): " typed </dev/tty || typed=""
  [ "$typed" = "$dev" ] || { echo "Cancelled. Nothing was changed."; return 1; }
  echo "Preparing the drive..."
  usb_format_drive "$dev" || return 1
  echo "Drive ready (ID $USB_NEW_UUID). Copying the existing backups to it..."
  usb_sync_all && echo "Done. The drive can stay plugged in, or be removed now."
}