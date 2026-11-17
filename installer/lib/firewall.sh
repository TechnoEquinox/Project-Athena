# shellcheck shell=bash
# Firewall: allow the library network only. Never locks out the current SSH session.

# plan_firewall CIDR SSH_CLIENT_IP -> prints ufw commands; returns 1 if the SSH session would be cut off.
plan_firewall() {
  local cidr="$1" client="${2:-}"
  if [ -n "$client" ] && ! ip_in_cidr "$client" "$cidr"; then
    return 1
  fi
  cat <<PLAN
default deny incoming
default allow outgoing
limit from $cidr to any port 22 proto tcp
allow from $cidr to any port 80,443 proto tcp
allow from $cidr to any port 443 proto udp
PLAN
}

apply_firewall() {
  local cidr="$1" line
  while IFS= read -r line; do
    # shellcheck disable=SC2086
    ufw $line >>"$LOG_FILE" 2>&1 || die "Firewall rule failed: ufw $line"
  done < <(plan_firewall "$cidr" "")
  ufw --force enable >>"$LOG_FILE" 2>&1 || die "Could not turn on the firewall."
  ok "Firewall is on: only $cidr can reach this server."
}
