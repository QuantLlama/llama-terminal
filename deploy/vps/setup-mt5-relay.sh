#!/usr/bin/env bash
# Install the MT5 bridge relay on the Coolify host (run on the VPS with sudo).
#
# Why this exists: Tailscale drops traffic that reaches tailnet addresses from
# non-tailnet interfaces, so a container cannot dial 100.x.y.z directly. The
# relay listens on the Docker bridge gateway (10.0.0.1 by default) and forwards
# to the tailnet peer that runs the MT5 bridge.
#
#   container -> 10.0.0.1:8081 -> socat -> <tailnet-peer>:8081
#
# Usage:
#   sudo ./setup-mt5-relay.sh                 # auto-discover the only online peer
#   sudo ./setup-mt5-relay.sh 100.101.102.103 # explicit peer address

set -euo pipefail

LISTEN_HOST="${LISTEN_HOST:-10.0.0.1}"
LISTEN_PORT="${LISTEN_PORT:-8081}"
TARGET_PORT="${TARGET_PORT:-8081}"
BRIDGE_CIDR="${BRIDGE_CIDR:-10.0.0.0/24}"
ENV_FILE="/etc/default/qllama-mt5-relay"
UNIT_FILE="/etc/systemd/system/qllama-mt5-relay.service"

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo." >&2
    exit 1
fi

if ! command -v socat >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y -qq socat
fi

peer="${1:-}"
if [[ -z "$peer" ]]; then
    peer="$(tailscale status --json 2>/dev/null \
        | python3 -c '
import json, sys
data = json.load(sys.stdin)
self_id = data.get("Self", {}).get("ID")
peers = [p for p in (data.get("Peer") or {}).values() if p.get("ID") != self_id]
online = [p for p in peers if p.get("Online")]
ips = [p["TailscaleIPs"][0] for p in online if p.get("TailscaleIPs")]
if len(ips) != 1:
    sys.stderr.write(f"expected exactly one online peer, found {len(ips)}: {ips}\n")
    sys.exit(1)
print(ips[0])
')" || {
        echo "Could not auto-discover the peer. Pass its tailnet IP explicitly." >&2
        exit 1
    }
fi

echo "Relaying ${LISTEN_HOST}:${LISTEN_PORT} -> ${peer}:${TARGET_PORT}"

cat > "$ENV_FILE" <<EOF
LISTEN_HOST=${LISTEN_HOST}
LISTEN_PORT=${LISTEN_PORT}
MT5_TARGET=${peer}:${TARGET_PORT}
EOF
chmod 644 "$ENV_FILE"

cat > "$UNIT_FILE" <<'EOF'
[Unit]
Description=Quantum Llama MT5 bridge relay (Docker gateway -> tailnet peer)
After=network-online.target tailscaled.service docker.service
Wants=network-online.target

[Service]
EnvironmentFile=/etc/default/qllama-mt5-relay
ExecStart=/usr/bin/socat TCP-LISTEN:${LISTEN_PORT},bind=${LISTEN_HOST},reuseaddr,fork TCP:${MT5_TARGET}
Restart=always
RestartSec=5
TimeoutStopSec=5

[Install]
WantedBy=multi-user.target
EOF

ufw allow from "$BRIDGE_CIDR" to "$LISTEN_HOST" port "$LISTEN_PORT" proto tcp \
    comment 'qllama-mt5-relay' >/dev/null

systemctl daemon-reload
systemctl enable --now qllama-mt5-relay.service
sleep 1
systemctl --no-pager --lines=0 status qllama-mt5-relay.service | head -5
ss -ltn | grep "${LISTEN_PORT}" || true
