#!/usr/bin/env bash
# Start the MT5 bridge on a Linux machine where MetaTrader 5 runs under Wine.
#
# Usage:
#   ./scripts/start_mt5_bridge.sh            # loopback only (desktop default)
#   MT5_BRIDGE_BIND=0.0.0.0 ./scripts/start_mt5_bridge.sh   # reachable via Tailscale
#
# The shared token is read from MT5_BRIDGE_TOKEN, or from
# ~/.config/qllama/mt5_bridge_token (created on first run when binding beyond
# loopback). The token is printed once so you can copy it into Coolify.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOKEN_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/qllama/mt5_bridge_token"
BIND="${MT5_BRIDGE_BIND:-127.0.0.1}"
PORT="${MT5_BRIDGE_PORT:-8081}"

if [[ -z "${MT5_BRIDGE_TOKEN:-}" ]]; then
    if [[ -f "$TOKEN_FILE" ]]; then
        MT5_BRIDGE_TOKEN="$(cat "$TOKEN_FILE")"
    elif [[ "$BIND" != "127.0.0.1" ]]; then
        mkdir -p "$(dirname "$TOKEN_FILE")"
        if command -v python3 >/dev/null 2>&1; then
            MT5_BRIDGE_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
        else
            MT5_BRIDGE_TOKEN="$(head -c 32 /dev/urandom | base64 | tr -d '=+/')"
        fi
        printf '%s' "$MT5_BRIDGE_TOKEN" > "$TOKEN_FILE"
        chmod 600 "$TOKEN_FILE"
        echo "Generated bridge token and stored it in $TOKEN_FILE"
    fi
fi

export MT5_BRIDGE_BIND="$BIND"
export MT5_BRIDGE_PORT="$PORT"
export MT5_BRIDGE_TOKEN="${MT5_BRIDGE_TOKEN:-}"

echo "Starting MT5 bridge on ${BIND}:${PORT}"
echo "Token configured: $([[ -n "${MT5_BRIDGE_TOKEN}" ]] && echo yes || echo no)"
if [[ -n "${MT5_BRIDGE_TOKEN}" ]]; then
    echo "Cloud variables for Coolify:"
    echo "  MT5_BRIDGE_URL=http://<this-machine-tailscale-ip>:${PORT}"
    echo "  MT5_BRIDGE_TOKEN=${MT5_BRIDGE_TOKEN}"
fi

cd "$ROOT_DIR"

if command -v wine >/dev/null 2>&1 && [[ -x "./venv/Scripts/python.exe" ]]; then
    exec wine ./venv/Scripts/python.exe -m uvicorn mt5_server:app --host "$BIND" --port "$PORT"
elif [[ -x "./venv_linux/bin/python" ]]; then
    exec ./venv_linux/bin/python -m uvicorn mt5_server:app --host "$BIND" --port "$PORT"
else
    exec python3 -m uvicorn mt5_server:app --host "$BIND" --port "$PORT"
fi
