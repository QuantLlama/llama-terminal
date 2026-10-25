#!/usr/bin/env bash
# Install the crypto egress relay on the Coolify host (run on the VPS with sudo).
#
# Binance answers HTTP 451 to this server's region, so crypto traffic is sent
# through the tailnet to a CONNECT proxy running on the operator's machine:
#
#   container -> 10.0.0.1:3128 -> socat -> <tailnet-peer>:3128 (CONNECT proxy)
#
# Usage:
#   sudo ./setup-crypto-proxy-relay.sh                    # auto-discover peer
#   sudo ./setup-crypto-proxy-relay.sh 100.101.102.103

set -euo pipefail

LISTEN_HOST="${LISTEN_HOST:-10.0.0.1}"
LISTEN_PORT="${LISTEN_PORT:-3128}"
TARGET_PORT="${TARGET_PORT:-3128}"
BRIDGE_CIDR="${BRIDGE_CIDR:-10.0.0.0/24}"
ENV_FILE="/etc/default/qllama-crypto-relay"
UNIT_FILE="/etc/systemd/system/qllama-crypto-relay.service"

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
PROXY_TARGET=${peer}:${TARGET_PORT}
EOF
chmod 644 "$ENV_FILE"

cat > "$UNIT_FILE" <<'EOF'
[Unit]
Description=Quantum Llama crypto egress relay (Docker gateway -> tailnet proxy)
After=network-online.target tailscaled.service docker.service
Wants=network-online.target

[Service]
EnvironmentFile=/etc/default/qllama-crypto-relay
# nodelay disables Nagle on the relay socket. The crypto feed is request/response
# heavy (ticker, trades and book every poll), so a stalled second segment turns
# into visible tape/DOM latency.
ExecStart=/usr/bin/socat TCP-LISTEN:${LISTEN_PORT},bind=${LISTEN_HOST},reuseaddr,fork,nodelay TCP:${PROXY_TARGET}
Restart=always
RestartSec=5
TimeoutStopSec=5

[Install]
WantedBy=multi-user.target
EOF

ufw allow from "$BRIDGE_CIDR" to "$LISTEN_HOST" port "$LISTEN_PORT" proto tcp \
    comment 'qllama-crypto-relay' >/dev/null

systemctl daemon-reload
systemctl enable --now qllama-crypto-relay.service
sleep 1
systemctl --no-pager --lines=0 status qllama-crypto-relay.service | head -5
ss -ltn | grep "${LISTEN_PORT}" || true
