"""Configuration tests for the MT5 HTTP bridge connector.

The cloud deployment must be able to target a remote bridge through
MT5_BRIDGE_URL and skip the local Wine auto-launch, while the local
development behaviour (127.0.0.1:8081 + auto-launch) stays unchanged.
"""

import importlib

import pytest


def _fresh_connector(monkeypatch, environ):
    # ``src.services.auth`` calls ``load_dotenv()`` at import, so a token from the
    # developer's .env would leak in and the "when unset" contract below would
    # silently test the opposite. Clear it unless this test sets it.
    for key in ("MT5_BRIDGE_URL", "MT5_AUTO_LAUNCH", "MT5_BRIDGE_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    for key, value in environ.items():
        monkeypatch.setenv(key, value)

    module = importlib.import_module("src.live.mt5_api_connector")
    module = importlib.reload(module)
    module.MT5ApiConnector._instance = None

    launches = []

    def fake_launch(self):
        launches.append(self.base_url)

    monkeypatch.setattr(module.MT5ApiConnector, "_ensure_server_running", fake_launch)
    return module, launches


def test_bridge_url_env_overrides_default_target(monkeypatch):
    module, launches = _fresh_connector(
        monkeypatch,
        {
            "MT5_BRIDGE_URL": "https://mt5.example.internal:8443",
            "MT5_AUTO_LAUNCH": "false",
        },
    )

    connector = module.MT5ApiConnector()

    assert connector.base_url == "https://mt5.example.internal:8443"
    assert connector.host == "mt5.example.internal"
    assert connector.port == 8443


def test_auto_launch_skipped_when_disabled(monkeypatch):
    module, launches = _fresh_connector(monkeypatch, {"MT5_AUTO_LAUNCH": "false"})

    module.MT5ApiConnector()

    assert launches == []


def test_local_defaults_preserved(monkeypatch):
    module, launches = _fresh_connector(monkeypatch, {})

    connector = module.MT5ApiConnector()

    assert connector.base_url == "http://127.0.0.1:8081"
    assert connector.host == "127.0.0.1"
    assert connector.port == 8081
    assert launches == ["http://127.0.0.1:8081"]


def test_auto_launch_still_default_when_env_missing(monkeypatch):
    module, _ = _fresh_connector(monkeypatch, {"MT5_AUTO_LAUNCH": "true"})
    launches = []

    def fake_launch(self):
        launches.append(self.base_url)
        # Preserve the real behaviour: no wait when already up.

    monkeypatch.setattr(module.MT5ApiConnector, "_ensure_server_running", fake_launch)
    module.MT5ApiConnector._instance = None

    module.MT5ApiConnector()

    assert launches == ["http://127.0.0.1:8081"]


def _headers_sent_by(connector, module):
    """Return the headers a real request would carry, without a network call."""
    import httpx

    seen = {}

    def handler(request):
        seen.update({key.lower(): value for key, value in request.headers.items()})
        return httpx.Response(200, json={"success": True})

    connector._client = httpx.Client(
        base_url=connector.base_url,
        transport=httpx.MockTransport(handler),
        event_hooks={"request": [connector._attach_bridge_auth]},
    )
    connector.connect()
    return seen


def test_bridge_token_header_sent_when_configured(monkeypatch):
    module, _ = _fresh_connector(
        monkeypatch, {"MT5_BRIDGE_TOKEN": "s3cret", "MT5_AUTO_LAUNCH": "false"}
    )

    connector = module.MT5ApiConnector()

    # The contract is what travels on the wire, not where the value is stored.
    assert _headers_sent_by(connector, module).get("x-bridge-token") == "s3cret"


def test_no_token_header_when_unset(monkeypatch):
    module, _ = _fresh_connector(monkeypatch, {"MT5_AUTO_LAUNCH": "false"})

    connector = module.MT5ApiConnector()

    assert "x-bridge-token" not in _headers_sent_by(connector, module)


class _RecordingClient:
    def __init__(self):
        self.posts = []

    def post(self, path, *args, **kwargs):
        self.posts.append(path)

        class _Response:
            status_code = 200

            @staticmethod
            def json():
                return {"success": True}

        return _Response()

    def get(self, path, *args, **kwargs):
        return self.post(path, *args, **kwargs)


def test_shutdown_does_not_tear_down_the_shared_bridge(monkeypatch):
    module, _ = _fresh_connector(monkeypatch, {"MT5_AUTO_LAUNCH": "false"})
    connector = module.MT5ApiConnector()
    recorder = _RecordingClient()
    connector._client = recorder
    connector.connected = True

    connector.shutdown()

    assert recorder.posts == [], "request-level shutdown must not POST /api/shutdown"
    assert connector.connected is False


def test_shutdown_bridge_is_explicit(monkeypatch):
    module, _ = _fresh_connector(monkeypatch, {"MT5_AUTO_LAUNCH": "false"})
    connector = module.MT5ApiConnector()
    recorder = _RecordingClient()
    connector._client = recorder
    connector.connected = True

    connector.shutdown_bridge()

    assert recorder.posts == ["/api/shutdown"]


def test_every_bridge_call_carries_the_token(monkeypatch):
    module, _ = _fresh_connector(
        monkeypatch, {"MT5_BRIDGE_TOKEN": "s3cret", "MT5_AUTO_LAUNCH": "false"}
    )
    connector = module.MT5ApiConnector()

    seen_headers = []

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            seen_headers.append(kwargs.get("headers"))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return FakeResponse()

        def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(module.httpx, "Client", FakeClient)

    connector.get_positions()
    connector.get_pending_orders()

    assert seen_headers, "expected the connector to open bridge connections"
    assert all(h and h.get("X-Bridge-Token") == "s3cret" for h in seen_headers), seen_headers


class _CatalogueClient:
    """Fake bridge that answers /api/symbols and counts calls."""

    calls = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, path, *args, **kwargs):
        _CatalogueClient.calls.append((path, kwargs.get("params")))

        catalogue = [
            {"name": "EURUSD", "path": "Forex\\EURUSD", "description": "Euro"},
            {"name": "NAS100", "path": "Indices\\NAS100", "description": "Nasdaq"},
        ]
        params = kwargs.get("params") or {}

        class _Response:
            status_code = 200

            @staticmethod
            def json():
                needle = (params.get("pattern") or "").lower()
                if needle:
                    return [s for s in catalogue if needle in s["name"].lower()]
                return catalogue

        return _Response()


def test_symbols_get_forwards_filters_and_caches_identical_calls(monkeypatch):
    module, _ = _fresh_connector(monkeypatch, {"MT5_AUTO_LAUNCH": "false"})
    connector = module.MT5ApiConnector()
    _CatalogueClient.calls = []
    monkeypatch.setattr(module.httpx, "Client", _CatalogueClient)

    first = connector.symbols_get(pattern="NAS")
    second = connector.symbols_get(pattern="NAS")
    other = connector.symbols_get(group="*")

    assert [s["name"] for s in first] == ["NAS100"]
    assert second == first
    assert len(other) == 2
    nas_calls = [c for c in _CatalogueClient.calls if c[1] and c[1].get("pattern") == "NAS"]
    assert len(nas_calls) == 1, f"identical lookups must be cached: {_CatalogueClient.calls}"
