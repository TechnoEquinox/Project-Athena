# shellcheck shell=bash
# Plain-language output helpers. No secrets are ever printed through these.

if [ -t 1 ]; then
  C_BOLD=$'\033[1m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_OFF=$'\033[0m'
else
  C_BOLD=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_OFF=""
fi

LOG_FILE="${LOG_FILE:-/var/log/athena-install.log}"

log()   { printf '%s %s\n' "$(date '+%F %T')" "$*" >>"$LOG_FILE" 2>/dev/null || true; }
step()  { printf '\n%s== %s ==%s\n' "$C_BOLD" "$*" "$C_OFF"; log "STEP $*"; }
say()   { printf '%s\n' "$*"; log "$*"; }
ok()    { printf '%s[ok]%s %s\n' "$C_GREEN" "$C_OFF" "$*"; log "OK $*"; }
warn()  { printf '%s[note]%s %s\n' "$C_YELLOW" "$C_OFF" "$*"; log "WARN $*"; }
die()   { printf '%s[stopped]%s %s\n' "$C_RED" "$C_OFF" "$*" >&2; log "FATAL $*"; exit 1; }

# ask "Question" "default" -> prints answer. In unattended mode (ATHENA_YES=1) returns the default.
ask() {
  local prompt="$1" default="${2:-}" reply
  if [ "${ATHENA_YES:-0}" = "1" ]; then printf '%s' "$default"; return 0; fi
  if [ -n "$default" ]; then
    read -r -p "$prompt [$default]: " reply </dev/tty || reply=""
  else
    read -r -p "$prompt: " reply </dev/tty || reply=""
  fi
  printf '%s' "${reply:-$default}"
}

# confirm "Question" "y|n" -> returns 0 for yes
confirm() {
  local prompt="$1" default="${2:-y}" reply hint="[Y/n]"
  [ "$default" = "n" ] && hint="[y/N]"
  if [ "${ATHENA_YES:-0}" = "1" ]; then [ "$default" = "y" ]; return; fi
  read -r -p "$prompt $hint: " reply </dev/tty || reply=""
  reply="${reply:-$default}"
  case "$reply" in [Yy]*) return 0 ;; *) return 1 ;; esac
}
