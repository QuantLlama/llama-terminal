"""The DISPLAY Wine gets must be a display that answers.

The bridge runs under a systemd user unit that only forwards the DISPLAY the
user manager knew at start time. When that is empty, Wine boots MetaTrader with
no driver ("nodrv_CreateWindow") and ``mt5.initialize()`` fails with IPC errors.
Exporting the first ``/tmp/.X11-unix/X*`` entry papers over that, but it also
hands Wine a dead socket left behind by a crashed X server, or another session's
display on a shared host. ``scripts/detect_x_display.sh`` is that decision,
extracted so it can be exercised without exec'ing uvicorn: it validates a live
socket, prefers a deterministic candidate, reports the matching XAUTHORITY, and
fails loudly when nothing validates.
"""

import os
import pathlib
import shutil
import socket
import subprocess
import threading
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "detect_x_display.sh"
LAUNCHER = ROOT / "scripts" / "start_mt5_bridge.sh"


def _run(sockets, home, *, display=None, xauthority=None, args=("--export",), **overrides):
    """Run the helper against a temp socket dir, never the real /tmp/.X11-unix."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "X11_SOCKET_DIR": str(sockets),
        "X11_XAUTH_RUN_DIR": str(home / "run-user"),
        # Keep the probe short: a validated socket that never replies is accepted,
        # so every case costs one timeout.
        "X11_PROBE_TIMEOUT": "0.1",
    }
    if display is not None:
        env["DISPLAY"] = display
    if xauthority is not None:
        env["XAUTHORITY"] = str(xauthority)
    env.update(overrides)
    return subprocess.run(
        ["bash", str(HELPER), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.fixture
def x11(tmp_path):
    """A temp X11 world: an empty socket dir, a home, and socket factories."""
    sockets = tmp_path / "X11-unix"
    sockets.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    (home / "run-user").mkdir()
    opened = []

    def live(name):
        """A listening Unix socket: what an X server leaves behind while alive."""
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(sockets / name))
        server.listen(4)
        opened.append(server)
        return sockets / name

    def dead(name):
        """A socket file with no listener: what a crashed X server leaves behind."""
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(sockets / name))
        server.close()
        return sockets / name

    yield SimpleNamespace(sockets=sockets, home=home, live=live, dead=dead)
    for server in opened:
        server.close()


def test_derives_a_live_display_and_its_authority(x11):
    x11.live("X0")
    authority = x11.home / ".Xauthority"
    authority.write_text("", encoding="utf-8")

    result = _run(x11.sockets, x11.home)

    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "export DISPLAY=':0'",
        f"export XAUTHORITY='{authority}'",
    ]
    assert result.stderr == ""


def test_fails_loudly_when_no_display_is_alive(x11):
    result = _run(x11.sockets, x11.home)

    assert result.returncode == 1, "a bridge without a display must not start silently"
    assert result.stdout == "", "exporting a dead DISPLAY is what this helper prevents"
    assert "no usable X display" in result.stderr


def test_rejects_a_stale_regular_file_matching_the_glob(x11):
    (x11.sockets / "X0").write_text("not a socket", encoding="utf-8")

    result = _run(x11.sockets, x11.home)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "no usable X display" in result.stderr


def test_rejects_a_socket_without_a_listener(x11):
    x11.dead("X0")

    result = _run(x11.sockets, x11.home)

    assert result.returncode == 1, "a socket file from a crashed X server is not a display"
    assert result.stdout == ""


def test_rejects_a_candidate_owned_by_another_uid(x11):
    x11.live("X0")

    result = _run(x11.sockets, x11.home, X11_EXPECTED_UID=str(os.getuid() + 1))

    assert result.returncode == 1, "a foreign display must never be handed to Wine"
    assert result.stdout == ""
    assert result.stderr == (
        f"detect_x_display.sh: no usable X display: nothing in {x11.sockets} "
        "is a live local X socket. Start a graphical session first, or set "
        "DISPLAY to a display that answers.\n"
    )


def test_warns_and_continues_when_no_probe_tool_is_available(x11):
    x11.live("X0")
    bindir = x11.home / "probe-less-bin"
    bindir.mkdir()
    for name in ("bash", "id", "stat", "sort", "grep", "awk", "xauth"):
        if found := shutil.which(name):
            (bindir / name).symlink_to(found)

    result = _run(
        x11.sockets, x11.home, PATH=str(bindir), X11_EXPECTED_UID=str(os.getuid())
    )

    assert result.returncode == 0, "a missing probe tool must not strand the bridge"
    assert result.stdout.splitlines() == ["export DISPLAY=':0'"]
    assert result.stderr == (
        "detect_x_display.sh: warning: cannot verify display :0 because neither "
        "python3 nor xdpyinfo is available; continuing\n"
    )


def test_keeps_a_live_display_from_the_environment(x11):
    x11.live("X0")
    x11.live("X7")

    result = _run(x11.sockets, x11.home, display=":7")

    assert result.returncode == 0
    assert result.stdout.splitlines()[0] == "export DISPLAY=':7'"


def test_replaces_a_dead_display_from_the_environment(x11):
    x11.live("X0")

    result = _run(x11.sockets, x11.home, display=":9")

    assert result.returncode == 0
    assert result.stdout.splitlines()[0] == "export DISPLAY=':0'"


def test_picks_the_live_candidate_when_the_first_glob_match_is_dead(x11):
    x11.dead("X0")
    x11.live("X1")

    result = _run(x11.sockets, x11.home)

    assert result.returncode == 0
    assert result.stdout.splitlines()[0] == "export DISPLAY=':1'"


def test_keeps_an_authority_from_the_environment(x11):
    x11.live("X0")
    (x11.home / ".Xauthority").write_text("", encoding="utf-8")
    custom = x11.home / "custom-xauthority"

    result = _run(x11.sockets, x11.home, xauthority=custom)

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["export DISPLAY=':0'", f"export XAUTHORITY='{custom}'"]


def test_reports_an_authority_by_query(x11):
    x11.live("X0")
    authority = x11.home / ".Xauthority"
    authority.write_text("", encoding="utf-8")

    assert _run(x11.sockets, x11.home, args=("--print-display",)).stdout == ":0\n"
    assert _run(x11.sockets, x11.home, args=("--print-xauthority",)).stdout == f"{authority}\n"


def _write_xauthority(directory, name, display, cookie):
    """Write a real Xauthority file: the format cannot be faked by hand."""
    xauth = shutil.which("xauth")
    if xauth is None:
        pytest.skip("xauth is not installed, so a per-session authority cannot be written")
    path = directory / name
    subprocess.run(
        [xauth, "-f", str(path), "add", display, ".", cookie * 32],
        check=True,
        capture_output=True,
    )
    return path


def _cookie_server(x11, name, cookie):
    """A fake X server that accepts the given MIT cookie and rejects others."""
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(x11.sockets / name))
    server.listen(8)

    def serve():
        while True:
            try:
                connection, _ = server.accept()
            except OSError:
                return
            with connection:
                try:
                    request = connection.recv(4096)
                    status = 1 if len(request) <= 12 or cookie in request else 3
                    connection.sendall(bytes([status, 0]) + b"\x0b\x00\x00\x00\x00\x00")
                except OSError:
                    pass

    threading.Thread(target=serve, daemon=True).start()
    return server


def test_claims_the_display_manager_authority_for_that_display(x11):
    authority = _write_xauthority(x11.home / "run-user", "xauth_1000", ":0", "0")
    x11.live("X0")

    result = _run(x11.sockets, x11.home)

    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "export DISPLAY=':0'",
        f"export XAUTHORITY='{authority}'",
    ]


def test_does_not_claim_an_authority_for_another_display(x11):
    _write_xauthority(x11.home / "run-user", "xauth_9", ":9", "1")
    x11.live("X0")

    result = _run(x11.sockets, x11.home)

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["export DISPLAY=':0'"], (
        "a cookie for another display must never be handed to Wine"
    )


def test_skips_an_authority_that_does_not_answer_for_the_display(x11):
    bad = _write_xauthority(x11.home, "bad-xauthority", ":0", "0")
    good = _write_xauthority(x11.home / "run-user", "xauth_1000", ":0", "1")
    server = _cookie_server(x11, "X0", b"\x11" * 16)
    try:
        result = _run(x11.sockets, x11.home, xauthority=bad)
    finally:
        server.close()

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["export DISPLAY=':0'", f"export XAUTHORITY='{good}'"]
    assert result.stderr == ""


def test_launcher_delegates_the_display_decision_to_the_helper():
    text = LAUNCHER.read_text(encoding="utf-8")

    assert "detect_x_display.sh" in text, "the launcher must use the validated helper"
    assert "/tmp/.X11-unix/X*" not in text, "the first-glob guess is what this replaces"
