# shellcheck shell=bash
# Installer step: install the server agent (lets admins manage the server from the web page).
# Needs ui.sh. Run from the repository root. Safe to run again.

: "${SBIN_DEST:=/usr/local/sbin}"
: "${STATE_DIR:=/var/lib/athena}"
: "${AGENT_REQUEST_UID:=1000}"   # the user ID the web app runs as inside its container

# The folders must exist BEFORE the containers start, because the web app mounts them.
prepare_agent_dirs() {
  install -d -m 755 "$STATE_DIR" "$STATE_DIR/agent" "$STATE_DIR/agent/out"
  install -d -m 700 -o "$AGENT_REQUEST_UID" -g "$AGENT_REQUEST_UID" "$STATE_DIR/agent/requests"
}

setup_agent() {
  prepare_agent_dirs
  install -m 755 installer/files/athena-agent "$SBIN_DEST/athena-agent"
  local f
  for f in athena-agent.path athena-agent.service athena-agent-health.service athena-agent-health.timer; do
    install -m 644 "installer/files/$f" "/etc/systemd/system/$f"
    sed -i "s|@INSTALL_DIR@|${INSTALL_DIR:-/opt/athena}|g" "/etc/systemd/system/$f"
  done
  systemctl daemon-reload >/dev/null 2>&1 || true
  systemctl enable --now athena-agent.path athena-agent-health.timer >>"${LOG_FILE:-/dev/null}" 2>&1 \
    || warn "Could not start the server agent. The Maintenance page will not work until it is running."
  ATHENA_DIR="${INSTALL_DIR:-/opt/athena}" "$SBIN_DEST/athena-agent" health >>"${LOG_FILE:-/dev/null}" 2>&1 || true
  ok "Server agent installed (powers the Maintenance page for administrators)."
}
