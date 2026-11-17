# shellcheck shell=bash
# Builds the .env file. NEVER overwrites an existing one (that would lock the
# database: its password would no longer match).

gen_hex()  { openssl rand -hex 24; }
gen_totp() { openssl rand -base64 32 | tr '+/' '-_'; }

# env_set FILE KEY VALUE : replace KEY=... line, or append if missing. Pure bash (values may contain = - _).
env_set() {
  local file="$1" key="$2" value="$3" line found=0 tmp
  tmp="$(mktemp "${file}.XXXXXX")"
  while IFS= read -r line || [ -n "$line" ]; do
    if [[ "$line" == "$key="* ]]; then
      printf '%s=%s\n' "$key" "$value" >>"$tmp"; found=1
    else
      printf '%s\n' "$line" >>"$tmp"
    fi
  done <"$file"
  [ "$found" = 1 ] || printf '%s=%s\n' "$key" "$value" >>"$tmp"
  cat "$tmp" >"$file"; rm -f "$tmp"
}

env_get() { grep -m1 "^$2=" "$1" 2>/dev/null | cut -d= -f2-; }

# write_env TEMPLATE TARGET HOST TIMEZONE FISCAL_MONTH
write_env() {
  local tmpl="$1" target="$2" host="$3" tz="$4" fy="$5"
  [ -f "$tmpl" ] || { echo "template $tmpl missing" >&2; return 1; }
  if [ -e "$target" ]; then echo "refusing to overwrite $target" >&2; return 1; fi
  ( umask 077; cp "$tmpl" "$target" )
  chmod 600 "$target"
  env_set "$target" POSTGRES_PASSWORD "$(gen_hex)"
  env_set "$target" APP_DB_PASSWORD "$(gen_hex)"
  env_set "$target" TOTP_ENCRYPTION_KEY "$(gen_totp)"
  env_set "$target" ATHENA_HOST "$host"
  env_set "$target" LIBRARY_TIMEZONE "$tz"
  env_set "$target" FISCAL_YEAR_START_MONTH "$fy"
  chmod 600 "$target"
}
