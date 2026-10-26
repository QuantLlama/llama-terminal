"""Behaviour of the Wine terminal launcher.

The launcher decides who owns MetaTrader 5. It must start ``wine`` when nothing
runs, and it must *wait* — never exit successfully — when another instance
already holds the terminal. Exiting successfully is what killed the unit under
``Restart=on-failure``: MT5 exits 0 on a clean shutdown, the unit stayed inactive
and the bridge booted a terminal of its own.
"""

import os
import pathlib
import stat
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "start_mt5_terminal.sh"


def _shim(directory, name, body):
    path = directory / name
    path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.fixture
def sandbox(tmp_path):
    """Launcher environment with fake ``wine``, ``pgrep`` and ``sleep``."""
    shims = tmp_path / "shims"
    shims.mkdir()
    state = {"wine": tmp_path / "wine-called", "pgrep_calls": tmp_path / "pgrep-calls"}
    terminal = tmp_path / "terminal64.exe"
    terminal.write_bytes(b"stub")
    # ``wine`` records that it was invoked and exits like a clean MT5 shutdown.
    _shim(shims, "wine", f'printf "%s\\n" "$@" > "{state["wine"]}"\nexit 0\n')
    # ``sleep`` does not really wait, so the wait loop runs at test speed.
    _shim(shims, "sleep", "exit 0\n")
    return {"shims": shims, "state": state, "terminal": terminal, "tmp": tmp_path}


def _run(sandbox, *, pgrep_exit, extra_env=None):
    """Run the launcher; ``pgrep`` answers ``pgrep_exit`` on every call."""
    calls = sandbox["state"]["pgrep_calls"]
    _shim(
        sandbox["shims"],
        "pgrep",
        f'printf x >> "{calls}"\nexit {pgrep_exit}\n',
    )
    env = {
        **os.environ,
        "PATH": f"{sandbox['shims']}:{os.environ['PATH']}",
        "DISPLAY": ":0",
        "MT5_EXE": str(sandbox["terminal"]),
    }
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", str(LAUNCHER)], capture_output=True, text=True, env=env, timeout=60
    )


def test_launcher_starts_wine_when_no_terminal_is_running(sandbox):
    result = _run(sandbox, pgrep_exit=1)

    assert result.returncode == 0, result.stderr
    assert sandbox["state"]["wine"].read_text().strip() == str(sandbox["terminal"])


def test_launcher_waits_instead_of_exiting_when_a_terminal_is_running(sandbox):
    """Two pgrep answers: running, then gone. Wine must run only after that."""
    calls = sandbox["state"]["pgrep_calls"]
    _shim(
        sandbox["shims"],
        "pgrep",
        # Record every call; the first reports a running instance, later ones do not.
        f'n=$(wc -c < "{calls}" 2>/dev/null || printf 0)\n'
        f'printf x >> "{calls}"\n'
        'if [[ "$n" -gt 0 ]]; then exit 1; fi\nexit 0\n',
    )
    env = {
        **os.environ,
        "PATH": f"{sandbox['shims']}:{os.environ['PATH']}",
        "DISPLAY": ":0",
        "MT5_EXE": str(sandbox["terminal"]),
    }

    result = subprocess.run(
        ["bash", str(LAUNCHER)], capture_output=True, text=True, env=env, timeout=60
    )

    assert result.returncode == 0, result.stderr
    assert "waiting for it to exit" in result.stdout
    assert sandbox["state"]["wine"].exists(), "wine must start once the other instance is gone"
    assert len(calls.read_text()) >= 2, "the launcher must re-check, not exit on the first answer"


def test_launcher_fails_loudly_when_the_executable_is_missing(sandbox):
    result = _run(
        sandbox,
        pgrep_exit=1,
        extra_env={"MT5_EXE": str(sandbox["tmp"] / "missing" / "terminal64.exe")},
    )

    assert result.returncode == 1
    assert "not found" in result.stderr
    assert not sandbox["state"]["wine"].exists()


@pytest.mark.skipif(
    any(pathlib.Path("/tmp/.X11-unix").glob("X*")),
    reason="an X socket exists on this machine, so display discovery cannot fail",
)
def test_launcher_fails_loudly_without_a_display(sandbox):
    result = _run(sandbox, pgrep_exit=1, extra_env={"DISPLAY": ""})

    assert result.returncode == 1
    assert "no X display" in result.stderr
    assert not sandbox["state"]["wine"].exists()
