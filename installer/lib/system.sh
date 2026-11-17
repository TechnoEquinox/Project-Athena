# shellcheck shell=bash
# Things that look at, or change, the machine.

detect_ip() {
  ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' | head -1
}

detect_cidr() {
  local ip addr
  ip="$(detect_ip)"; [ -n "$ip" ] || return 1
  addr="$(ip -4 -o addr show | awk -v ip="$ip" '{split($4,a,"/"); if (a[1]==ip) print $4}' | head -1)"
  [ -n "$addr" ] && cidr_of "$addr"
}

detect_timezone() {
  local tz
  tz="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
  [ -n "$tz" ] && [ "$tz" != "UTC" ] && [ "$tz" != "Etc/UTC" ] && { printf '%s' "$tz"; return; }
  printf 'America/New_York'
}

preflight() {
  [ "$(id -u)" -eq 0 ] || die "Please run this with sudo:  sudo ./install.sh"
  [ -r /etc/os-release ] || die "Cannot tell which operating system this is."
  # shellcheck disable=SC1091
  . /etc/os-release
  [ "${ID:-}" = "ubuntu" ] || die "Athena's installer supports Ubuntu Server only (this is: ${PRETTY_NAME:-unknown})."
  local major="${VERSION_ID%%.*}"
  [ "${major:-0}" -ge 22 ] || die "Ubuntu 22.04 or newer is required (this is $VERSION_ID)."
  [ "$(uname -m)" = "x86_64" ] || [ "$(uname -m)" = "aarch64" ] || die "Unsupported CPU type: $(uname -m)."
  local free_gb ram_mb
  free_gb="$(df -BG --output=avail / | tail -1 | tr -dc '0-9')"
  [ "${free_gb:-0}" -ge 10 ] || die "At least 10 GB of free disk space is needed (found ${free_gb} GB)."
  ram_mb="$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)"
  [ "${ram_mb:-0}" -ge 1800 ] || warn "Only ${ram_mb} MB of memory found. 2 GB or more is recommended."
  ok "Ubuntu $VERSION_ID, ${free_gb} GB free disk, ${ram_mb} MB memory."
}

check_internet() {
  if curl -fsS --max-time 10 -o /dev/null https://registry-1.docker.io/v2/ 2>/dev/null || \
     curl -sS --max-time 10 -o /dev/null -w '%{http_code}' https://registry-1.docker.io/v2/ 2>/dev/null | grep -q 401; then
    ok "Internet access works (needed once, to download software)."
  else
    die "Could not reach the internet. The installer needs to download Docker images. Check the server's network and try again."
  fi
}

apt_fail() {
  printf '\nThe last lines of the log:\n' >&2
  tail -n 15 "$LOG_FILE" >&2
  die "$1 The full log is in $LOG_FILE."
}

install_packages() {
  export DEBIAN_FRONTEND=noninteractive
  say "Updating the package list..."
  apt-get update -qq >>"$LOG_FILE" 2>&1 || apt_fail "apt-get update failed."

  say "Installing helper tools..."
  apt-get install -y -qq curl openssl ufw python3 ca-certificates cron >>"$LOG_FILE" 2>&1 \
    || apt_fail "Installing helper tools failed."

  if command -v docker >/dev/null 2>&1; then
    ok "Docker is already installed - keeping it as it is."
  else
    say "Installing Docker (this can take a few minutes)..."
    apt-get install -y -qq docker.io docker-compose-v2 >>"$LOG_FILE" 2>&1 \
      || apt_fail "Installing Docker failed."
  fi

  systemctl enable --now docker >>"$LOG_FILE" 2>&1 || die "Could not start Docker."
  docker compose version >/dev/null 2>&1 \
    || die "Docker is installed but the 'docker compose' command is missing. Install the Docker Compose plugin (package docker-compose-plugin or docker-compose-v2), then run this installer again."
  ok "Docker is installed and running."
}

report_encryption() {
  if lsblk -no TYPE 2>/dev/null | grep -q crypt; then
    ok "Disk encryption detected on this server."
  else
    warn "This server's disk is NOT encrypted. That is acceptable only if the server is physically secured (locked room). Patron records are stored on it. See SECURITY.md."
  fi
}

report_dhcp() {
  if grep -rqs "dhcp4: *\(true\|yes\)" /etc/netplan/ 2>/dev/null; then
    warn "This server gets its address automatically (DHCP). If the address changes, staff will lose access. Ask your IT contact for a fixed address or a DHCP reservation."
  fi
}
