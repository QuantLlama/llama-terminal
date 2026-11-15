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
#   X11_EXPECTED_UID   uid that must own the socket    (default: id -u)
#
# Exit status: 0 when a display was validated, 1 when none could be (stderr says
# why), 2 for a usage error.
set -euo pipefail

X11_SOCKET_DIR="${X11_SOCKET_DIR:-/tmp/.X11-unix}"
X11_XAUTH_RUN_DIR="${X11_XAUTH_RUN_DIR:-/run/user/$(id -u)}"
X11_PROBE_TIMEOUT="${X11_PROBE_TIMEOUT:-0.3}"
X11_EXPECTED_UID="${X11_EXPECTED_UID:-$(id -u)}"

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
probe_tool_available() {
    command -v python3 >/dev/null 2>&1 || command -v xdpyinfo >/dev/null 2>&1
}

# A display manager running as root owns the socket file even when the session
# belongs to the operator (system X servers on Arch and Debian do exactly that),
# so the file owner alone cannot decide who the display belongs to. Root is
# therefore always acceptable, and the authenticated probe below is what proves
# the session is really the operator's: Wine only gets in with their cookie.
socket_owned_by_expected_uid() {
    local owner
    owner="$(stat -c '%u' "$1" 2>/dev/null || stat -f '%u' "$1" 2>/dev/null)" || return 1
    [[ "$owner" == "$X11_EXPECTED_UID" || "$owner" == "0" ]]
}

warn_unverified_display() {
    printf 'detect_x_display.sh: warning: cannot verify display %s because neither python3 nor xdpyinfo is available; continuing\n' \
        "$1" >&2
}

x_server_answers() {
    local socket="$1" number="${2:-}" authority="${3:-}" mode="${4:-}"
    local cookie=""
    if [[ -z "$mode" ]]; then
        if [[ -n "$authority" ]]; then mode="auth"; else mode="live"; fi
    fi
    if [[ "$mode" == "auth" && -n "$authority" ]]; then
        cookie="$(xauth_cookie "$authority" "$number")" || cookie=""
    fi
    if command -v python3 >/dev/null 2>&1; then
        X11_PROBE_COOKIE="$cookie" python3 - "$socket" "$X11_PROBE_TIMEOUT" "$mode" <<'PROBE'
import os
import socket
import struct
import sys

path, timeout, mode = sys.argv[1], float(sys.argv[2]), sys.argv[3]
data = bytes.fromhex(os.environ.get("X11_PROBE_COOKIE", ""))
name = b"MIT-MAGIC-COOKIE-1" if data else b""
request = b"l\x00" + struct.pack("<HHHH", 11, 0, len(name), len(data)) + b"\x00\x00"
request += name + b"\x00" * (-len(name) % 4)
request += data + b"\x00" * (-len(data) % 4)
probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
probe.settimeout(timeout)
try:
    probe.connect(path)
except OSError:
    sys.exit(1)

reply = b""
try:
    probe.sendall(request)
    reply = probe.recv(8)
except OSError:
    pass
finally:
    probe.close()

if not reply:
    # A silent server is not a rejection, and the old behaviour tolerated it.
    sys.exit(0)
if mode == "auth":
    sys.exit(0 if reply[0] == 1 else 1)
sys.exit(0 if reply[0] in (0, 1) else 1)
PROBE
        return
    fi
    # No python3: fall back to the X client that ships with x11-utils.
    command -v xdpyinfo >/dev/null 2>&1 || return 1
    if [[ "$mode" == "auth" && -n "$authority" ]]; then
        XAUTHORITY="$authority" xdpyinfo -display ":${socket##*/X}" >/dev/null 2>&1
    else
        XAUTHORITY=/dev/null xdpyinfo -display ":${socket##*/X}" >/dev/null 2>&1
    fi
}

resolve_display() {
    local candidate number have_probe=0
    probe_tool_available && have_probe=1
    # An existing DISPLAY wins, but only when it points at a live local socket
    # owned by the expected uid: a dead or foreign value is worse than none
    # because Wine then fails without a reason.
    if [[ -n "${DISPLAY:-}" ]]; then
        if candidate="$(socket_for_display "$DISPLAY")" \
            && [[ -S "$candidate" ]] \
            && socket_owned_by_expected_uid "$candidate" \
            && { [[ "$have_probe" == 0 ]] || x_server_answers "$candidate"; }; then
            [[ "$have_probe" == 1 ]] || warn_unverified_display "$DISPLAY"
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
        candidate="$X11_SOCKET_DIR/X$number"
        socket_owned_by_expected_uid "$candidate" || continue
        if [[ "$have_probe" == 0 ]]; then
            warn_unverified_display ":$number"
            printf ':%s' "$number"
            return 0
        fi
        if x_server_answers "$candidate"; then
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

# The MIT cookie a file holds for a display, as hex, for the probe to carry.
xauth_cookie() {
    local file="$1" number="$2"
    command -v xauth >/dev/null 2>&1 || return 1
    xauth -f "$file" list ":$number" 2>/dev/null \
        | awk '$2 == "MIT-MAGIC-COOKIE-1" { print $3; exit }'
}

# The authority for the validated display. Every candidate is proved against
# the display; a mismatched file is skipped instead of being paired with it, and
# with no candidate at all the server needs no authority.
resolve_xauthority() {
    local socket="$1" number="$2" candidate
    local candidates=()
    if [[ -n "${XAUTHORITY:-}" ]]; then
        candidates+=("$XAUTHORITY")
    fi
    if [[ -r "$HOME/.Xauthority" ]]; then
        candidates+=("$HOME/.Xauthority")
    fi
    for candidate in "$X11_XAUTH_RUN_DIR"/xauth_*; do
        [[ -f "$candidate" && -r "$candidate" ]] || continue
        if xauth_owns_display "$candidate" "$number"; then
            candidates+=("$candidate")
        fi
    done
    if ! probe_tool_available; then
        # Without a probe tool the pair cannot be proved; keep the old best guess.
        printf '%s' "${candidates[0]:-}"
        return 0
    fi
    for candidate in ${candidates[@]+"${candidates[@]}"}; do
        if x_server_answers "$socket" "$number" "$candidate"; then
            printf '%s' "$candidate"
            return 0
        fi
    done
    if [[ ${#candidates[@]} -eq 0 ]] \
        && x_server_answers "$socket" "$number" "" auth; then
        printf ''
        return 0
    fi
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
if ! authority="$(resolve_xauthority "$X11_SOCKET_DIR/X$number" "$number")"; then
    die "no usable X display: no X authority for $display answers for it. Set XAUTHORITY to a cookie for $display, or start a new graphical session."
fi
xauthority="$authority"

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
