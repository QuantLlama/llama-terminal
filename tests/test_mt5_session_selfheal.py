"""Session liveness for the MT5 native connector.

``connected`` is a one-way flag: nothing clears it when the terminal restarts or
logs out. The bridge therefore kept answering from a dead session while the
platform showed an empty chart, and only a manual service restart brought the
data back. These tests pin the recovery the bridge needs to heal itself.
"""

import importlib
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _StubMt5Module(types.ModuleType):
    """Minimal MetaTrader5 stand-in; unpatched attributes resolve to ``0``."""

    def __getattr__(self, name):
        return 0


def _native_connector(monkeypatch):
    """Fresh native connector with ``connected`` already trusted, like the bridge."""
    monkeypatch.setitem(sys.modules, "MetaTrader5", _StubMt5Module("MetaTrader5"))
    for name in ("src.live.mt5_native_connector",):
        monkeypatch.delitem(sys.modules, name, raising=False)
    module = importlib.import_module("src.live.mt5_native_connector")
    module.MT5Connector._instance = None
    connector = module.MT5Connector()
    connector.connected = True
    return module, connector, sys.modules["MetaTrader5"]


def _counting(monkeypatch, stub, *, initialize_ok=True, alive_after_init=True, alive_before_init=False):
    """Wire ``initialize``/``shutdown``/``terminal_info`` and count the calls."""
    calls = {"initialize": 0, "shutdown": 0}

    def initialize(*args, **kwargs):
        calls["initialize"] += 1
        return initialize_ok

    def shutdown():
        calls["shutdown"] += 1

    def terminal_info():
        # A restarted terminal has no IPC session until initialize() runs again.
        if alive_before_init or (calls["initialize"] and alive_after_init):
            return {"build": 4000}
        return None

    monkeypatch.setattr(stub, "initialize", initialize, raising=False)
    monkeypatch.setattr(stub, "shutdown", shutdown, raising=False)
    monkeypatch.setattr(stub, "terminal_info", terminal_info, raising=False)
    monkeypatch.setattr(stub, "last_error", lambda: (-10001, "IPC send failed"), raising=False)
    return calls


def test_is_alive_is_false_when_the_terminal_does_not_answer(monkeypatch):
    _, connector, stub = _native_connector(monkeypatch)
    monkeypatch.setattr(stub, "terminal_info", lambda: None, raising=False)

    assert connector.is_alive() is False


def test_is_alive_is_false_when_the_flag_is_down_even_if_the_terminal_answers(monkeypatch):
    _, connector, stub = _native_connector(monkeypatch)
    monkeypatch.setattr(stub, "terminal_info", lambda: {"build": 4000}, raising=False)
    connector.connected = False

    assert connector.is_alive() is False


def test_connect_leaves_a_live_session_alone(monkeypatch):
    _, connector, stub = _native_connector(monkeypatch)
    calls = _counting(monkeypatch, stub, alive_before_init=True)

    assert connector.connect() is True
    assert calls["initialize"] == 0
    assert connector.connected is True


def test_connect_reinitializes_a_session_whose_terminal_restarted(monkeypatch):
    _, connector, stub = _native_connector(monkeypatch)
    calls = _counting(monkeypatch, stub)

    assert connector.connect() is True
    assert calls["initialize"] == 1
    assert calls["shutdown"] == 1
    assert connector.connected is True


def test_connect_clears_the_flag_when_the_terminal_cannot_come_back(monkeypatch):
    _, connector, stub = _native_connector(monkeypatch)
    calls = _counting(monkeypatch, stub, initialize_ok=False)

    assert connector.connect() is False
    assert calls["initialize"] == 1
    assert connector.connected is False


class _ProbeConnector:
    """Connector with a liveness probe, like the native one."""

    def __init__(self, alive, raises=False):
        self.connected = True
        self.calls = 0
        self._alive = alive
        self._raises = raises

    def is_alive(self):
        if self._raises:
            raise RuntimeError("IPC send failed")
        return self._alive

    def connect(self):
        self.calls += 1
        self.connected = True
        return True


def test_ensure_connected_reconnects_when_the_probe_reports_dead():
    from src.live.mt5_bridge_session import ensure_connected

    connector = _ProbeConnector(alive=False)

    assert ensure_connected(connector) is True
    assert connector.calls == 1


def test_ensure_connected_treats_a_raising_probe_as_dead():
    from src.live.mt5_bridge_session import ensure_connected

    connector = _ProbeConnector(alive=True, raises=True)

    assert ensure_connected(connector) is True
    assert connector.calls == 1


def test_ensure_connected_leaves_a_probe_alive_session_alone():
    from src.live.mt5_bridge_session import ensure_connected

    connector = _ProbeConnector(alive=True)

    assert ensure_connected(connector) is True
    assert connector.calls == 0
