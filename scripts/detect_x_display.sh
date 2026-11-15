#!/usr/bin/env bash
# Resolve a usable local X display for Wine, or fail loudly.
#
# Why this exists: the bridge unit forwards DISPLAY/XAUTHORITY through
# PassEnvironment, but the systemd user manager only knows what its own
# environment had when it started. With an empty DISPLAY, Wine boots the terminal
# with no driver ("nodrv_CreateWindow") and mt5.initialize() fails with IPC
# errors. Exporting the first /tmp/.X11-unix/X* entry is not enough either: after
# an X crash the socket file outlives its server, and on a host with several
# sessions the first file may belong to a different display. This helper accepts
# a display only when its socket is a Unix socket that a local X server still
# answers on, picks the candidate deterministically, and reports the Xauthority
# that goes with it.
#
# Usage:
#   ./scripts/detect_x_display.sh --export            # shell assignments, ready for eval
#   ./scripts/detect_x_display.sh --print-display     # just the display, e.g. :0
#   ./scripts/detect_x_display.sh --print-xauthority  # the matching authority, or nothing
#
# Tunables (the tests point these at a temp directory):
#   X11_SOCKET_DIR     where X keeps its sockets       (default /tmp/.X11-unix)
#   X11_XAUTH_RUN_DIR  display-manager authority dir   (default /run/user/<uid>)
#   X11_PROBE_TIMEOUT  seconds to wait for a server reply while probing (default 0.3)
#
# Exit status: 0 when a display was validated, 1 when none could be (stderr says
# why), 2 for a usage error.
set -euo pipefail

X11_SOCKET_DIR="${X11_SOCKET_DIR:-/tmp/.X11-unix}"
X11_XAUTH_RUN_DIR="${X11_XAUTH_RUN_DIR:-/run/user/$(id -u)}"
X11_PROBE_TIMEOUT="${X11_PROBE_TIMEOUT:-0.3}"

usage() {
    # Everything above the first executable line is the help text.
    awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "${BASH_SOURCE[0]}"
}

die() {
    printf 'detect_x_display.sh: %s\n' "$1" >&2
    exit 1
}

# Socket path for a local display string, or failure when DISPLAY points
# somewhere this machine cannot validate (host:N is not our Unix socket).
socket_for_display() {
    local display="$1" number
    case "$display" in
        :*|unix:*) ;;
        *) return 1 ;;
    esac
    number="${display##*:}"
    number="${number%%.*}"
    [[ "$number" =~ ^[0-9]+$ ]] || return 1
    printf '%s/X%s' "$X11_SOCKET_DIR" "$number"
}

# A display is usable only when its socket accepts a connection and a local X
# server answers on it. A stale socket file from a crashed X server refuses the
# connection, which is exactly the case the old first-glob guess got wrong.
x_server_answers() {
    local socket="$1"
    if command -v python3 >/dev/null 2>&1; then
        python3 - "$socket" "$X11_PROBE_TIMEOUT" <<'PROBE'
import socket
import sys

path, timeout = sys.argv[1], float(sys.argv[2])
probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
probe.settimeout(timeout)
try:
    probe.connect(path)
except OSError:
    sys.exit(1)

reply = b""
try:
    # Connection setup: little-endian, protocol 11.0, no auth of our own. A reply
    # proves a server owns the socket; status 0 (auth required) and 1 (success)
    # are both real answers. Silence is tolerated: a slow server is not a dead
    # one, and the authority is checked separately.
    probe.sendall(b"l\x00\x0b\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")
    reply = probe.recv(8)
except OSError:
    pass
finally:
    probe.close()

sys.exit(0 if not reply or reply[0] in (0, 1) else 1)
PROBE
        return
    fi
    # No python3: fall back to the X client that ships with x11-utils.
    command -v xdpyinfo >/dev/null 2>&1 || return 1
    xdpyinfo -display ":${socket##*/X}" >/dev/null 2>&1
}

resolve_display() {
    local candidate number
    # An existing DISPLAY wins, but only when it points at a live local socket:
    # a dead value is worse than none because Wine then fails without a reason.
    if [[ -n "${DISPLAY:-}" ]]; then
        if candidate="$(socket_for_display "$DISPLAY")" \
            && [[ -S "$candidate" ]] \
            && x_server_answers "$candidate"; then
            printf '%s' "$DISPLAY"
            return 0
        fi
        printf "detect_x_display.sh: ignoring DISPLAY='%s' (not a live local X socket)\n" \
            "$DISPLAY" >&2
    fi
    # Otherwise pick deterministically: the lowest-numbered display that
    # validates, never whatever the shell happened to glob first.
    local numbers=()
    mapfile -t numbers < <(
        for candidate in "$X11_SOCKET_DIR"/X*; do
            [[ -S "$candidate" ]] || continue
            number="${candidate##*/X}"
            [[ "$number" =~ ^[0-9]+$ ]] || continue
            printf '%s\n' "$number"
        done | sort -n -u
    )
    for number in ${numbers[@]+"${numbers[@]}"}; do
        if x_server_answers "$X11_SOCKET_DIR/X$number"; then
            printf ':%s' "$number"
            return 0
        fi
    done
    return 1
}

# Does this authority file carry a cookie for that display?
xauth_owns_display() {
    local file="$1" number="$2"
    command -v xauth >/dev/null 2>&1 || return 1
    xauth -f "$file" list 2>/dev/null | grep -Eq ":$number(\\.[0-9]+)?[[:space:]]"
}

# The authority that belongs to the validated display. An existing value wins;
# otherwise the operator's own file, otherwise the display manager's per-session
# file, and only when it actually lists that display.
resolve_xauthority() {
    local number="$1" candidate
    if [[ -n "${XAUTHORITY:-}" ]]; then
        printf '%s' "$XAUTHORITY"
        return 0
    fi
    if [[ -r "$HOME/.Xauthority" ]]; then
        printf '%s' "$HOME/.Xauthority"
        return 0
    fi
    for candidate in "$X11_XAUTH_RUN_DIR"/xauth_*; do
        [[ -f "$candidate" && -r "$candidate" ]] || continue
        if xauth_owns_display "$candidate" "$number"; then
            printf '%s' "$candidate"
            return 0
        fi
    done
    return 1
}

MODE="${1:---export}"
case "$MODE" in
    --export|--print-display|--print-xauthority) ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'usage: %s [--export|--print-display|--print-xauthority]\n' "${0##*/}" >&2; exit 2 ;;
esac

display="$(resolve_display)" || die "no usable X display: nothing in $X11_SOCKET_DIR is a live local X socket. Start a graphical session first, or set DISPLAY to a display that answers."
number="${display##*:}"
number="${number%%.*}"
xauthority=""
if authority="$(resolve_xauthority "$number")"; then
    xauthority="$authority"
fi

case "$MODE" in
    --export)
        printf "export DISPLAY='%s'\n" "$display"
        if [[ -n "$xauthority" ]]; then
            printf "export XAUTHORITY='%s'\n" "$xauthority"
        fi
        ;;
    --print-display)
        printf '%s\n' "$display"
        ;;
    --print-xauthority)
        if [[ -n "$xauthority" ]]; then
            printf '%s\n' "$xauthority"
        fi
        ;;
esac
