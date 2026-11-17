# shellcheck shell=bash
# Pure functions: easy to test, no side effects.

# A hostname (athena.library.lan) or an IPv4 address.
valid_host() {
  local h="${1:-}"
  [ -n "$h" ] && [ "${#h}" -le 253 ] || return 1
  if [[ "$h" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    python3 -c 'import ipaddress,sys; ipaddress.IPv4Address(sys.argv[1])' "$h" 2>/dev/null
    return
  fi
  [[ "$h" =~ ^[0-9.]+$ ]] && return 1   # digits and dots that are not a valid IPv4 address
  [[ "$h" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$ ]]
}

# A network like 192.168.1.0/24
valid_cidr() {
  python3 -c 'import ipaddress,sys; ipaddress.IPv4Network(sys.argv[1], strict=True)' "${1:-}" 2>/dev/null
}

# ip_in_cidr IP CIDR -> 0 if inside
ip_in_cidr() {
  python3 -c '
import ipaddress, sys
sys.exit(0 if ipaddress.IPv4Address(sys.argv[1]) in ipaddress.IPv4Network(sys.argv[2], strict=False) else 1)
' "${1:-}" "${2:-}" 2>/dev/null
}

# cidr_of ADDR/PREFIX -> network, e.g. 192.168.1.23/24 -> 192.168.1.0/24
cidr_of() {
  python3 -c 'import ipaddress,sys; print(ipaddress.IPv4Interface(sys.argv[1]).network)' "${1:-}" 2>/dev/null
}

valid_month() { [[ "${1:-}" =~ ^([1-9]|1[0-2])$ ]]; }

valid_timezone() {
  python3 -c 'import zoneinfo,sys; zoneinfo.ZoneInfo(sys.argv[1])' "${1:-}" 2>/dev/null
}

# Fiscal year default for a month: Connecticut libraries commonly use July.
# Extract the client address from an SSH_CLIENT-style string ("1.2.3.4 5555 22").
ssh_client_ip() { printf '%s' "${1:-}" | awk '{print $1}'; }
