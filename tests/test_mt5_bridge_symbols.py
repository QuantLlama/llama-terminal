"""Symbol catalogue plumbing for the MT5 HTTP bridge.

The cloud deployment reaches MetaTrader 5 only through ``mt5_server.py``, so the
symbol list must travel native connector -> bridge route -> HTTP connector ->
``/api/symbols``. These tests pin the three links and the token requirement.
"""

import collections
import importlib
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _StubMt5Module(types.ModuleType):
    """Minimal MetaTrader5 stand-in.

    ``mt5_server`` imports the native connector, which imports MetaTrader5 at
    module level. On Linux that import fails, so tests install this stub in
    ``sys.modules`` and delete the cached connector/bridge modules before
    importing them. Unpatched attributes resolve to ``0`` the way unused MT5
    constants would.
    """

    def __getattr__(self, name):
        return 0


def _stub_missing_uvicorn(monkeypatch):
    """Stub uvicorn when the test venv lacks it.

    ``mt5_server`` imports uvicorn only to serve the app under ``__main__``; the
    declared deploy dependency (requirements.deploy.txt) provides it, so the
    route tests do not need the real server runner.
    """
    try:
        importlib.import_module("uvicorn")
    except ModuleNotFoundError:
        monkeypatch.setitem(sys.modules, "uvicorn", types.ModuleType("uvicorn"))


FakeSymbol = collections.namedtuple(
    "FakeSymbol",
    ["name", "description", "path", "visible", "trade_mode", "expiration_time"],
)


def _install_stub_mt5(monkeypatch):
    _stub_missing_uvicorn(monkeypatch)
    stub = _StubMt5Module("MetaTrader5")
    monkeypatch.setitem(sys.modules, "MetaTrader5", stub)
    for name in ("src.live.mt5_native_connector", "mt5_server"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    return stub


def _native_connector(monkeypatch):
    stub = _install_stub_mt5(monkeypatch)
    module = importlib.import_module("src.live.mt5_native_connector")
    module.MT5Connector._instance = None
    connector = module.MT5Connector()
    connector.connected = True
    return module, connector, stub


def test_native_symbols_get_returns_empty_list_when_mt5_raises(monkeypatch):
    _, connector, stub = _native_connector(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("terminal unavailable")

    monkeypatch.setattr(stub, "symbols_get", boom, raising=False)

    assert connector.symbols_get(group="*USD*") == []


def test_native_symbols_get_returns_empty_list_when_mt5_yields_nothing(monkeypatch):
    _, connector, stub = _native_connector(monkeypatch)
    monkeypatch.setattr(stub, "symbols_get", lambda *a, **k: None, raising=False)

    assert connector.symbols_get() == []


def test_native_symbols_get_returns_plain_dicts_and_honours_pattern(monkeypatch):
    _, connector, stub = _native_connector(monkeypatch)
    catalogue = [
        FakeSymbol("EURUSD", "Euro vs US Dollar", "Forex\\EURUSD", True, 4, 0),
        FakeSymbol("XAUUSD", "Gold vs US Dollar", "Metals\\XAUUSD", True, 4, 0),
    ]
    monkeypatch.setattr(stub, "symbols_get", lambda *a, **k: catalogue, raising=False)

    result = connector.symbols_get(pattern="euru")

    assert result == [
        {
            "name": "EURUSD",
            "description": "Euro vs US Dollar",
            "path": "Forex\\EURUSD",
            "visible": True,
            "trade_mode": 4,
            "expiration_time": 0,
        }
    ]
    # The pattern also matches the symbol path, as the MT5 group glob did.
    assert [s["name"] for s in connector.symbols_get(pattern="metals")] == ["XAUUSD"]


def _fresh_api_connector(monkeypatch, environ):
    for key in ("MT5_BRIDGE_URL", "MT5_AUTO_LAUNCH", "MT5_BRIDGE_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    for key, value in environ.items():
        monkeypatch.setenv(key, value)

    module = importlib.import_module("src.live.mt5_api_connector")
    module = importlib.reload(module)
    module.MT5ApiConnector._instance = None

    monkeypatch.setattr(module.MT5ApiConnector, "_ensure_server_running", lambda self: None)
    return module


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _install_fake_httpx(monkeypatch, module, response):
    seen = {"headers": [], "calls": []}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            seen["headers"].append(kwargs.get("headers"))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, path, *args, **kwargs):
            seen["calls"].append((path, kwargs))
            return response

        def post(self, *args, **kwargs):
            raise AssertionError("symbols_get must not POST")

    monkeypatch.setattr(module.httpx, "Client", FakeClient)
    return seen


def test_api_symbols_get_sends_token_and_returns_empty_on_error_payload(monkeypatch):
    module = _fresh_api_connector(
        monkeypatch, {"MT5_BRIDGE_TOKEN": "s3cret", "MT5_AUTO_LAUNCH": "false"}
    )
    connector = module.MT5ApiConnector()
    seen = _install_fake_httpx(monkeypatch, module, _FakeResponse({"detail": "invalid bridge token"}, 401))

    assert connector.symbols_get(group="*USD*", pattern="USD") == []
    assert seen["headers"], "expected the connector to open a bridge connection"
    assert all(h and h.get("X-Bridge-Token") == "s3cret" for h in seen["headers"]), seen["headers"]
    path, kwargs = seen["calls"][0]
    assert path == "/api/symbols"
    # Filters travel to the bridge so a slow tunnel only carries the matches.
    assert kwargs["params"] == {"group": "*USD*", "pattern": "USD"}


def test_api_symbols_get_ignores_dict_payload_with_status_200(monkeypatch):
    module = _fresh_api_connector(monkeypatch, {"MT5_AUTO_LAUNCH": "false"})
    connector = module.MT5ApiConnector()
    _install_fake_httpx(monkeypatch, module, _FakeResponse({"detail": "boom"}, 200))

    assert connector.symbols_get() == []


def test_native_symbols_get_keeps_default_market_watch_call(monkeypatch):
    _, connector, stub = _native_connector(monkeypatch)
    calls = []

    def record(*args, **kwargs):
        calls.append((args, kwargs))
        return []

    monkeypatch.setattr(stub, "symbols_get", record, raising=False)

    connector.symbols_get()

    assert calls == [((), {})], "unfiltered lookups must stay the default MT5 call"


def test_bridge_route_allows_local_calls_when_no_token_configured(monkeypatch):
    from fastapi.testclient import TestClient

    _install_stub_mt5(monkeypatch)
    bridge = importlib.import_module("mt5_server")
    monkeypatch.setattr(
        bridge.connector,
        "symbols_get",
        lambda group=None, pattern=None: [{"name": "EURUSD"}],
    )
    monkeypatch.delenv("MT5_BRIDGE_TOKEN", raising=False)

    response = TestClient(bridge.app).get("/api/symbols")

    assert response.status_code == 200
    assert response.json() == [{"name": "EURUSD"}]


def test_bridge_symbols_route_requires_token(monkeypatch):
    from fastapi.testclient import TestClient

    _install_stub_mt5(monkeypatch)
    bridge = importlib.import_module("mt5_server")
    monkeypatch.setattr(
        bridge.connector,
        "symbols_get",
        lambda group=None, pattern=None: [{"name": "EURUSD"}],
    )

    client = TestClient(bridge.app)

    monkeypatch.setenv("MT5_BRIDGE_TOKEN", "s3cret")
    unauthorized = client.get("/api/symbols")
    assert unauthorized.status_code == 401
    assert unauthorized.json() == {"detail": "invalid bridge token"}

    authorized = client.get("/api/symbols", headers={"X-Bridge-Token": "s3cret"})
    assert authorized.status_code == 200
    assert authorized.json() == [{"name": "EURUSD"}]
