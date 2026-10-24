"""Configuration tests for the MT5 HTTP bridge connector.

The cloud deployment must be able to target a remote bridge through
MT5_BRIDGE_URL and skip the local Wine auto-launch, while the local
development behaviour (127.0.0.1:8081 + auto-launch) stays unchanged.
"""

import importlib

import pytest


def _fresh_connector(monkeypatch, environ):
    for key in ("MT5_BRIDGE_URL", "MT5_AUTO_LAUNCH"):
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
