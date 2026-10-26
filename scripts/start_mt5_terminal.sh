#!/usr/bin/env bash
# Start the MetaTrader 5 terminal inside Wine.
#
# The terminal has to run inside the graphical session: without an X display
# Wine fails with "nodrv_CreateWindow" and every mt5.initialize() answers
# "IPC send failed", which is what made the bridge serve a dead session.
#
# Usage:
#   ./scripts/start_mt5_terminal.sh
#   MT5_EXE=/path/to/terminal64.exe ./scripts/start_mt5_terminal.sh

set -euo pipefail

MT5_EXE="${MT5_EXE:-${WINEPREFIX:-$HOME/.wine}/drive_c/Program Files/MetaTrader 5/terminal64.exe}"

# Resolve the display instead of hardcoding :0, so this survives a switch
# between X11 and Wayland sessions and any other seat number.
resolve_display() {
    if [[ -n "${DISPLAY:-}" ]]; then
        printf '%s' "$DISPLAY"
        return 0
    fi
    local socket
    for socket in /tmp/.X11-unix/X*; do
        if [[ -S "$socket" ]]; then
            printf ':%s' "${socket##*/X}"
            return 0
        fi
    done
    return 1
}

if ! display="$(resolve_display)"; then
    echo "no X display found: Wine cannot create the terminal window" >&2
    exit 1
fi
export DISPLAY="$display"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"

if [[ ! -f "$MT5_EXE" ]]; then
    echo "MetaTrader 5 not found at $MT5_EXE" >&2
    exit 1
fi

# Exit successfully when the terminal already runs: a second wine start would
# compete for the same data profile and take the session away from the bridge,
# which is already connected to the running terminal. Match the executable name
# that is actually configured, not just the default one.
if pgrep -f -- "$(basename "$MT5_EXE")" >/dev/null 2>&1; then
    echo "MetaTrader 5 is already running; nothing to do"
    exit 0
fi

exec wine "$MT5_EXE"
