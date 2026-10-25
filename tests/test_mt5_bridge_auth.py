"""Tests for the MT5 bridge transport security layer.

The bridge is reachable from the cloud app once a tunnel is in place, so it
must support a shared token while keeping the local-only default unauthenticated
behaviour (127.0.0.1, no token) unchanged.
"""

import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_client(monkeypatch, environ):
    for key in ("MT5_BRIDGE_TOKEN", "MT5_BRIDGE_BIND", "MT5_BRIDGE_PORT"):
        monkeypatch.delenv(key, raising=False)
    for key, value in environ.items():
        monkeypatch.setenv(key, value)

    module = importlib.reload(importlib.import_module("src.live.mt5_bridge_auth"))

    app = FastAPI()
    app.middleware("http")(module.require_bridge_token)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return module, TestClient(app)


def test_request_without_token_is_rejected_when_token_configured(monkeypatch):
    _, client = _build_client(monkeypatch, {"MT5_BRIDGE_TOKEN": "s3cret"})

    response = client.get("/ping")

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid bridge token"}


def test_request_with_wrong_token_is_rejected(monkeypatch):
    _, client = _build_client(monkeypatch, {"MT5_BRIDGE_TOKEN": "s3cret"})

    response = client.get("/ping", headers={"X-Bridge-Token": "wrong"})

    assert response.status_code == 401


def test_request_with_valid_token_passes(monkeypatch):
    _, client = _build_client(monkeypatch, {"MT5_BRIDGE_TOKEN": "s3cret"})

    response = client.get("/ping", headers={"X-Bridge-Token": "s3cret"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_local_default_requires_no_token(monkeypatch):
    _, client = _build_client(monkeypatch, {})

    response = client.get("/ping")

    assert response.status_code == 200


def test_bind_defaults_to_loopback(monkeypatch):
    module, _ = _build_client(monkeypatch, {})

    assert module.bridge_bind() == ("127.0.0.1", 8081)


def test_bind_reads_environment(monkeypatch):
    module, _ = _build_client(
        monkeypatch, {"MT5_BRIDGE_BIND": "0.0.0.0", "MT5_BRIDGE_PORT": "9099"}
    )

    assert module.bridge_bind() == ("0.0.0.0", 9099)


def test_api_connector_reads_the_token_at_request_time(monkeypatch):
    """The bridge token must be read per request, not frozen at construction.

    ``src/live/connector.py`` instantiates this connector while the module is
    imported, which happens before ``load_dotenv()`` runs. Freezing the headers in
    ``__init__`` therefore built a client with no ``X-Bridge-Token``, and every
    ``connect()`` answered 401: the platform reported ``MT5 CONNECTION FAILED``
    for a bridge that was healthy.
    """
    import httpx

    from src.live.mt5_api_connector import MT5ApiConnector

    monkeypatch.delenv("MT5_BRIDGE_TOKEN", raising=False)
    connector = MT5ApiConnector(base_url="http://127.0.0.1:9")

    seen = {}

    def handler(request):
        seen.update({key.lower(): value for key, value in request.headers.items()})
        return httpx.Response(200, json={"success": True})

    connector._client = httpx.Client(
        base_url="http://127.0.0.1:9",
        transport=httpx.MockTransport(handler),
        event_hooks={"request": [connector._attach_bridge_auth]},
    )

    # The token appears only after the client was built, exactly like .env.
    monkeypatch.setenv("MT5_BRIDGE_TOKEN", "late-token")
    assert connector.connect() is True
    assert seen.get("x-bridge-token") == "late-token"
