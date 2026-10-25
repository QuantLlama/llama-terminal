#!/usr/bin/env bash
# Keep a local port forward to the cloud Postgres alive, self-resolving.
#
# The cloud Postgres is a container inside the VPS docker network: it has no
# public port, and its IP changes whenever Coolify recreates it. Hardcoding the
# address means the tunnel silently dies and every per-user route starts
# answering 500, so this script asks the VPS for the current address on every
# start and then forwards to it.
#
# Usage:
#   qllama-pg-tunnel.sh                 # run the tunnel (systemd uses this)
#   qllama-pg-tunnel.sh --print-target  # just resolve and show what it would use
#
# Environment:
#   QLLAMA_VPS_HOST      ssh destination (default: qllama-vps from ~/.ssh/config)
#   QLLAMA_VPS_KEY       private key to use (auto-detected when unset)
#   QLLAMA_PG_CONTAINER  postgres container name (default: detected)
#   QLLAMA_PG_PORT       local port (default: 5433)
set -euo pipefail

VPS_HOST="${QLLAMA_VPS_HOST:-qllama-vps}"
LOCAL_PORT="${QLLAMA_PG_PORT:-5433}"
PG_CONTAINER="${QLLAMA_PG_CONTAINER:-}"
REMOTE_PORT=5432

ssh_args=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)

# A key that moved must not break the tunnel: look in the usual places and keep
# the first one that actually authenticates.
if [[ -z "${QLLAMA_VPS_KEY:-}" ]]; then
    for candidate in "$HOME/.ssh/qllama_vps" "$HOME/.ssh/id_ed25519_vps" "$HOME/Descargas/awspass.pem" "$HOME/.ssh/id_ed25519"; do
        if [[ -f "$candidate" ]]; then
            if ssh -i "$candidate" "${ssh_args[@]}" -o ConnectTimeout=5 "$VPS_HOST" true 2>/dev/null; then
                QLLAMA_VPS_KEY="$candidate"
                break
            fi
        fi
    done
fi
if [[ -z "${QLLAMA_VPS_KEY:-}" ]]; then
    echo "no usable ssh key for $VPS_HOST; set QLLAMA_VPS_KEY" >&2
    exit 1
fi
ssh_cmd=(ssh -i "$QLLAMA_VPS_KEY" "${ssh_args[@]}" "$VPS_HOST")
remote() { "${ssh_cmd[@]}" "$@"; }

# The database the application actually uses is the one named in its own
# DATABASE_URL: matching containers by the word "postgres" picks the Coolify
# database instead, which is a different host entirely.
if [[ -z "$PG_CONTAINER" ]]; then
    APP_CONTAINER="$(remote "sudo -n docker ps --format '{{.Names}}' | grep -E 'zzkdpzudy7gp42gfxcffday4' | head -n1")"
    if [[ -n "$APP_CONTAINER" ]]; then
        PG_CONTAINER="$(remote "sudo -n docker exec $APP_CONTAINER printenv DATABASE_URL" \
            | sed -E 's#^[a-z]+://[^@]*@##; s#[:/].*$##')"
    fi
fi
if [[ -z "$PG_CONTAINER" ]]; then
    echo "could not determine the database host on $VPS_HOST" >&2
    exit 1
fi

# A container can sit on several networks; print one address per line and keep
# the first private one instead of concatenating them all.
PG_IP="$(remote "sudo -n docker inspect $PG_CONTAINER --format '{{range \$name, \$net := .NetworkSettings.Networks}}{{println \$net.IPAddress}}{{end}}'" \
    | grep -E '^10\.[0-9]+\.[0-9]+\.[0-9]+$' | head -n1)"
if [[ -z "$PG_IP" ]]; then
    echo "could not resolve the address of $PG_CONTAINER" >&2
    exit 1
fi

if [[ "${1:-}" == "--print-target" ]]; then
    echo "$PG_CONTAINER -> $PG_IP:$REMOTE_PORT via $VPS_HOST, local port $LOCAL_PORT"
    exit 0
fi

if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -q "127.0.0.1:${LOCAL_PORT} "; then
    echo "port $LOCAL_PORT is already in use; refusing to start" >&2
    exit 1
fi

echo "forwarding 127.0.0.1:${LOCAL_PORT} -> ${PG_CONTAINER} (${PG_IP}:${REMOTE_PORT}) via ${VPS_HOST}"
exec "${ssh_cmd[@]}" -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -N -L "127.0.0.1:${LOCAL_PORT}:${PG_IP}:${REMOTE_PORT}"
