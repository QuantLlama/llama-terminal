#!/usr/bin/env bash
# Install the bridge runtime on the system disk.
#
# Why this exists: the repository lives on an encrypted removable volume, and
# systemd user units cannot start from a directory that does not exist yet. The
# two local bridges only need six files, so they run from a copy under the home
# directory and start at boot without the volume being unlocked.
#
# Usage:
#   ./scripts/install_bridge_runtime.sh           # copy the runtime files
#   ./scripts/install_bridge_runtime.sh --check   # report drift, exit 1 on drift
#
# The repository stays the source of truth: re-run this script after changing any
# of the files listed below, and `--check` tells you when the copy is stale.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${QLLAMA_RUNTIME_DIR:-$HOME/.local/share/qllama/runtime}"
MODE="install"
if [[ "${1:-}" == "--check" ]]; then
    MODE="check"
elif [[ $# -gt 0 ]]; then
    echo "usage: $0 [--check]" >&2
    exit 2
fi

# Runtime files, relative to the repository root. Keep this list minimal: it is
# everything mt5_server.py and local_crypto_proxy.py import.
RUNTIME_FILES=(
    "mt5_server.py"
    "scripts/start_mt5_bridge.sh"
    "scripts/local_crypto_proxy.py"
    "scripts/qllama-pg-tunnel.sh"
    "src/__init__.py"
    # src/live has no __init__.py: it is a namespace package.
    "src/live/mt5_native_connector.py"
    "src/live/mt5_bridge_auth.py"
    "src/live/mt5_bridge_session.py"
)

drift=0
for relative in "${RUNTIME_FILES[@]}"; do
    source_file="$ROOT_DIR/$relative"
    target_file="$TARGET_DIR/$relative"
    if [[ ! -f "$source_file" ]]; then
        echo "missing in repository: $relative" >&2
        exit 1
    fi
    if [[ "$MODE" == "check" ]]; then
        if ! cmp -s "$source_file" "$target_file"; then
            echo "stale: $relative"
            drift=1
        fi
        continue
    fi
    case "$relative" in
        *.sh) install -D -m 0755 "$source_file" "$target_file" ;;
        *)    install -D -m 0644 "$source_file" "$target_file" ;;
    esac
done

if [[ "$MODE" == "check" ]]; then
    if [[ "$drift" -eq 0 ]]; then
        echo "runtime up to date: $TARGET_DIR"
    fi
    exit "$drift"
fi

echo "bridge runtime installed in $TARGET_DIR"
echo "systemd units: qllama-crypto-proxy.service, qllama-mt5-bridge.service"
