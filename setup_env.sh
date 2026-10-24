#!/bin/bash
# Linux/macOS setup. Run from the project root; never source user activation code.

recreate=false
help=false
for arg in "$@"; do
    case "$arg" in
        --recreate) recreate=true ;;
        --help) help=true ;;
        *) printf 'Error: unknown argument: %s\n' "$arg" >&2; exit 2 ;;
    esac
done
if "$help"; then
    printf '%s\n' \
        'Usage: ./setup_env.sh [--recreate | --help]' \
        'Create or reuse venv_linux; fall back to XDG_DATA_HOME/quantumllama.' \
        '--recreate  Replace only a validated, owned virtual environment.' \
        '--help      Show this help without changing files.'
    exit 0
fi

fail() { printf 'Error: %s\n' "$1" >&2; exit "${2:-1}"; }
unsafe() { fail "refusing unsafe virtual environment: $1"; }

# Reject symlinks in directory components too (including dangling links).
safe_path() {
    local part="$1"
    case "/$part/" in */../*) return 1 ;; esac
    while [ "$part" != / ] && [ "$part" != . ]; do
        [ ! -L "$part" ] || return 1
        [ ! -e "$part" ] || [ -d "$part" ] || return 1
        case "$part" in
            */*) part="${part%/*}"; [ -n "$part" ] || part=/ ;;
            *) part=. ;;
        esac
    done
}

valid_venv() {
    local path="$1"
    [ -d "$path" ] && [ -O "$path" ] &&
        [ -f "$path/pyvenv.cfg" ] && [ -O "$path/pyvenv.cfg" ] &&
        [ ! -L "$path/pyvenv.cfg" ] &&
        [ -d "$path/bin" ] && [ ! -L "$path/bin" ] && [ -O "$path/bin" ] &&
        [ -f "$path/bin/activate" ] && [ ! -L "$path/bin/activate" ] &&
        [ -O "$path/bin/activate" ] && [ -x "$path/bin/python" ] &&
        "$path/bin/python" -c 'import os, sys; sys.exit(not (sys.prefix != sys.base_prefix and os.path.realpath(sys.prefix) == os.path.realpath(sys.argv[1])))' "$path" >/dev/null 2>&1
}

fallback_root="${XDG_DATA_HOME:-${HOME}/.local/share}/quantumllama"
fallback="$fallback_root/venv_linux"
VENV_PATH=./venv_linux
recorded=
if [ -e .venv_linux_path ] || [ -L .venv_linux_path ]; then
    [ -f .venv_linux_path ] && [ ! -L .venv_linux_path ] &&
        [ -O .venv_linux_path ] || fail 'invalid .venv_linux_path.'
    recorded=$(< .venv_linux_path)
    case "$recorded" in
        ./venv_linux|"$fallback") VENV_PATH="$recorded" ;;
        *) fail 'invalid .venv_linux_path.' ;;
    esac
fi

prepare_target() {
    local path="$1"
    if [ "$path" = "$fallback" ]; then
        case "$path" in /*) ;; *) unsafe "$path" ;; esac
    fi
    safe_path "$path" || unsafe "$path"
    if [ -e "$path" ]; then
        valid_venv "$path" || unsafe "$path"
        if "$recreate"; then
            # Exact allowlisted target, owned and validated above; rm does not
            # traverse symlinks contained inside this directory.
            rm -rf -- "$path" || fail 'virtual environment removal failed.'
            # The opt-in authorizes one replacement, not a second environment
            # if local creation subsequently fails and selects the fallback.
            recreate=false
        fi
    fi
}

prepare_target "$VENV_PATH"
created=false
if [ ! -d "$VENV_PATH" ]; then
    if [ "$VENV_PATH" = ./venv_linux ] && python3 -m venv "$VENV_PATH"; then
        created=true
    else
        VENV_PATH="$fallback"
        prepare_target "$VENV_PATH"
        if [ ! -d "$VENV_PATH" ]; then
            mkdir -p -- "$fallback_root" || fail 'fallback directory creation failed.'
            python3 -m venv "$VENV_PATH" || fail 'virtual environment creation failed.'
            created=true
        fi
    fi
fi
valid_venv "$VENV_PATH" || unsafe "$VENV_PATH"

if [ -f requirements.txt ]; then
    "$VENV_PATH/bin/python" -m pip install --upgrade pip || fail 'pip upgrade failed.' "$?"
    "$VENV_PATH/bin/python" -m pip install -r requirements.txt || fail 'requirements installation failed.' "$?"
fi

# Atomic replacement avoids following an existing hard link when recording.
if [ "$recorded" != "$VENV_PATH" ]; then
    pointer=$(mktemp .venv_linux_path.XXXXXX) || fail 'could not record environment path.'
    trap 'rm -f -- "$pointer"' EXIT
    printf '%s\n' "$VENV_PATH" > "$pointer" && mv -f -- "$pointer" .venv_linux_path ||
        fail 'could not record environment path.'
    trap - EXIT
fi
printf 'Setting up environment...\n'
if "$created"; then
    if [ "$VENV_PATH" = ./venv_linux ]; then
        printf 'Virtual environment creado localmente con éxito.\n'
    else
        printf 'Created virtual environment: %s\n' "$VENV_PATH"
    fi
else
    printf 'Reusing virtual environment: %s\n' "$VENV_PATH"
fi
if [ -f requirements.txt ]; then
    printf 'Requirements installed.\n'
else
    printf 'requirements.txt not found.\n'
fi
printf 'Setup complete.\n'
