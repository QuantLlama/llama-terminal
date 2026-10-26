"""The bridge must not boot the MT5 terminal unless a person is using the platform.

Background polling used to boot it: ``ensure_mt5_session`` calls
``mt5.initialize()`` on every request, and the MT5 Python API launches
``terminal64.exe`` whenever no terminal answers. The cloud MarketDataEngine polls
about once per second, so closing the terminal brought a new one back seconds
later. These tests pin the demand lease, the boot gate and the routes that expose
them.
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
    """Minimal MetaTrader5 stand-in; unpatched constants resolve to ``0``."""

    def __getattr__(self, name):
        return 0


def _install_stub_mt5(monkeypatch):
    try:
        importlib.import_module("uvicorn")
    except ModuleNotFoundError:
        monkeypatch.setitem(sys.modules, "uvicorn", types.ModuleType("uvicorn"))
    monkeypatch.setitem(sys.modules, "MetaTrader5", _StubMt5Module("MetaTrader5"))
    for name in ("src.live.mt5_native_connector", "mt5_server"):
        monkeypatch.delitem(sys.modules, name, raising=False)


def _bridge(monkeypatch):
    _install_stub_mt5(monkeypatch)
    return importlib.import_module("mt5_server")


def _demand_module():
    return importlib.import_module("src.live.mt5_terminal_demand")


class _Clock:
    """Monotonic clock the tests advance by hand."""

    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class _Demand:
    """Stand-in with a fixed answer, for the gate tests."""

    def __init__(self, active):
        self._active = active

    def active(self):
        return self._active

    def remaining(self):
        return 30.0 if self._active else 0.0


def _connector(usable):
    calls = []

    class _Connector:
        connected = usable

        def is_alive(self):
            return usable

        def connect(self, path=None):
            calls.append(path)
            return False

    return _Connector(), calls


# ── Lease ────────────────────────────────────────────────────────────────────


def test_demand_starts_inactive():
    module = _demand_module()
    demand = module.TerminalDemand(ttl=lambda: 120.0, clock=_Clock())

    assert demand.active() is False
    assert demand.remaining() == 0.0


def test_renew_keeps_the_lease_active_until_the_ttl_expires():
    module = _demand_module()
    clock = _Clock()
    demand = module.TerminalDemand(ttl=lambda: 120.0, clock=clock)

    assert demand.renew() == 120.0
    clock.advance(119.0)
    assert demand.active() is True

    clock.advance(1.0)
    assert demand.active() is False, "an expired lease must not authorise a boot"


def test_renew_extends_an_already_active_lease():
    module = _demand_module()
    clock = _Clock()
    demand = module.TerminalDemand(ttl=lambda: 120.0, clock=clock)

    demand.renew()
    clock.advance(100.0)
    demand.renew()
    clock.advance(100.0)

    assert demand.active() is True
    assert demand.remaining() == pytest.approx(20.0)


def test_revoke_clears_an_active_lease():
    module = _demand_module()
    demand = module.TerminalDemand(ttl=lambda: 120.0, clock=_Clock())
    demand.renew()

    demand.revoke()

    assert demand.active() is False


@pytest.mark.parametrize("raw", ["", "0", "-5", "not-a-number"])
def test_ttl_falls_back_to_the_default_for_unusable_values(monkeypatch, raw):
    module = _demand_module()
    monkeypatch.setenv(module.TTL_ENV, raw)

    assert module.demand_ttl() == module.DEFAULT_TTL_SECONDS


def test_ttl_reads_a_positive_value_from_the_environment(monkeypatch):
    module = _demand_module()
    monkeypatch.setenv(module.TTL_ENV, "45")

    assert module.demand_ttl() == 45.0


# ── Boot gate ────────────────────────────────────────────────────────────────


def test_gate_allows_the_boot_while_demand_is_active():
    module = _demand_module()
    connector, _ = _connector(usable=False)

    assert module.allow_terminal_boot(connector, _Demand(True), probe=lambda: False) is True


def test_gate_withholds_the_boot_without_demand_and_no_terminal():
    module = _demand_module()
    connector, _ = _connector(usable=False)

    assert module.allow_terminal_boot(connector, _Demand(False), probe=lambda: False) is False


def test_gate_allows_the_boot_when_the_terminal_already_runs():
    module = _demand_module()
    connector, _ = _connector(usable=False)

    assert module.allow_terminal_boot(connector, _Demand(False), probe=lambda: True) is True


def test_gate_withholds_the_boot_when_the_process_table_cannot_be_read():
    module = _demand_module()
    connector, _ = _connector(usable=False)

    # Fail closed: a disarmed probe must not recreate the boot loop it exists to stop.
    assert module.allow_terminal_boot(connector, _Demand(False), probe=lambda: None) is False


def test_gate_skips_the_probe_when_the_session_is_already_usable():
    module = _demand_module()
    connector, _ = _connector(usable=True)

    def explode():
        raise AssertionError("a live session must not probe the process table")

    assert module.allow_terminal_boot(connector, _Demand(False), probe=explode) is True


# ── Bridge routes ────────────────────────────────────────────────────────────


def _pin_demand(monkeypatch, bridge, *, ttl=120.0):
    module = _demand_module()
    clock = _Clock()
    demand = module.TerminalDemand(ttl=lambda: ttl, clock=clock)
    monkeypatch.setattr(bridge, "terminal_demand", demand)
    return demand, clock


def test_demand_route_extends_the_lease_and_reports_expiry(monkeypatch):
    from fastapi.testclient import TestClient

    bridge = _bridge(monkeypatch)
    demand, _ = _pin_demand(monkeypatch, bridge)

    response = TestClient(bridge.app).post("/api/terminal/demand")

    assert response.status_code == 200
    assert response.json() == {"active": True, "expires_in": pytest.approx(120.0)}
    assert demand.active() is True


def test_status_route_reports_the_terminal_and_the_lease(monkeypatch):
    from fastapi.testclient import TestClient

    bridge = _bridge(monkeypatch)
    demand, _ = _pin_demand(monkeypatch, bridge)
    monkeypatch.setattr(bridge, "terminal_process_running", lambda: False)
    monkeypatch.setattr(bridge.connector, "is_alive", lambda: False)

    idle = TestClient(bridge.app).get("/api/terminal/status").json()
    assert idle["terminal_running"] is False
    assert idle["demand_active"] is False
    assert idle["session_alive"] is False

    demand.renew()
    busy = TestClient(bridge.app).get("/api/terminal/status").json()
    assert busy["terminal_running"] is False
    assert busy["demand_active"] is True
    assert busy["demand_remaining_seconds"] == pytest.approx(120.0)


def test_data_route_does_not_boot_the_terminal_without_demand(monkeypatch):
    from fastapi.testclient import TestClient

    bridge = _bridge(monkeypatch)
    _pin_demand(monkeypatch, bridge)
    monkeypatch.setattr(bridge, "terminal_process_running", lambda: False)
    calls = []
    monkeypatch.setattr(bridge.connector, "connect", _recorder(calls))
    monkeypatch.setattr(bridge.connector, "symbols_get", lambda *a, **k: [{"name": "EURUSD"}])

    response = TestClient(bridge.app).get("/api/symbols")

    # The gate withholds the boot trigger only: the route contract is unchanged.
    assert response.status_code == 200
    assert response.json() == [{"name": "EURUSD"}]
    assert calls == [], "polling must never call connect()"


def test_data_route_boots_the_terminal_while_demand_is_active(monkeypatch):
    from fastapi.testclient import TestClient

    bridge = _bridge(monkeypatch)
    demand, _ = _pin_demand(monkeypatch, bridge)
    demand.renew()
    monkeypatch.setattr(bridge, "terminal_process_running", lambda: False)
    calls = []
    monkeypatch.setattr(bridge.connector, "connect", _recorder(calls))
    monkeypatch.setattr(bridge.connector, "symbols_get", lambda *a, **k: [{"name": "EURUSD"}])

    response = TestClient(bridge.app).get("/api/symbols")

    assert response.status_code == 200
    assert calls == [None], "an open browser session is what authorises the boot"


def test_shutdown_route_never_touches_the_terminal_session(monkeypatch):
    from fastapi.testclient import TestClient

    bridge = _bridge(monkeypatch)
    _pin_demand(monkeypatch, bridge)
    calls = []
    monkeypatch.setattr(bridge.connector, "connect", _recorder(calls))
    monkeypatch.setattr(bridge.connector, "shutdown", lambda: None)

    response = TestClient(bridge.app).post("/api/shutdown")

    assert response.status_code == 200
    assert calls == []


def test_terminal_routes_require_the_bridge_token(monkeypatch):
    from fastapi.testclient import TestClient

    bridge = _bridge(monkeypatch)
    _pin_demand(monkeypatch, bridge)
    client = TestClient(bridge.app)
    monkeypatch.setenv("MT5_BRIDGE_TOKEN", "s3cret")

    assert client.post("/api/terminal/demand").status_code == 401

    authorized = client.post("/api/terminal/demand", headers={"X-Bridge-Token": "s3cret"})
    assert authorized.status_code == 200


# ── Helpers used by the route tests ──────────────────────────────────────────


def _recorder(calls):
    def connect(path=None):
        calls.append(path)
        return False

    return connect


def test_release_route_revokes_the_lease_without_touching_the_terminal(monkeypatch):
    from fastapi.testclient import TestClient

    bridge = _bridge(monkeypatch)
    demand, _ = _pin_demand(monkeypatch, bridge)
    demand.renew()
    calls = []
    monkeypatch.setattr(bridge.connector, "connect", _recorder(calls))
    monkeypatch.setattr(bridge.connector, "shutdown", lambda: None)

    response = TestClient(bridge.app).delete("/api/terminal/demand")

    assert response.status_code == 200
    assert response.json() == {"active": False}
    assert demand.active() is False, "a closed session must not keep the lease alive"
    assert calls == [], "releasing the lease must never touch the terminal"
