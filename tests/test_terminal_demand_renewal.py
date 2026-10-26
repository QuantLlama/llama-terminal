"""Only an open platform session may authorise the MT5 terminal to boot.

The bridge boots ``terminal64.exe`` through ``mt5.initialize()`` when no terminal
answers, so the platform must renew the bridge's demand lease exactly while a
browser session is connected: nothing else (services startup, market-data
polling, a running algorithm) is a person using the platform.
"""

import asyncio
import importlib
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def services(monkeypatch):
    """``services_api`` with its connection counters and renewal task reset."""
    monkeypatch.setenv("MT5_AUTO_LAUNCH", "false")
    module = importlib.import_module("src.platform.api.services_api")
    monkeypatch.setattr(module, "_active_connections", 0, raising=False)
    monkeypatch.setattr(module, "_demand_task", None, raising=False)

    async def _never():
        return None

    monkeypatch.setattr(module, "_check_auto_shutdown", _never)
    monkeypatch.setattr(module, "_shutdown_task", None, raising=False)
    yield module
    task = getattr(module, "_demand_task", None)
    if task is not None and not task.done():
        task.cancel()
    module._demand_task = None
    module._active_connections = 0


class _FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


def _install_fake_httpx(monkeypatch, module, seen, status_code=200):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            seen.setdefault("timeouts", []).append(kwargs.get("timeout"))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, **kwargs):
            seen.setdefault("posts", []).append((url, kwargs.get("headers")))
            return _FakeResponse(status_code)

        def delete(self, url, **kwargs):
            seen.setdefault("deletes", []).append((url, kwargs.get("headers")))
            return _FakeResponse(status_code)

    monkeypatch.setattr(module.httpx, "Client", FakeClient)


def _api_connector(monkeypatch, *, token="s3cret", url="http://127.0.0.1:8081"):
    for key in ("MT5_BRIDGE_URL", "MT5_BRIDGE_TOKEN", "MT5_AUTO_LAUNCH"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MT5_AUTO_LAUNCH", "false")
    if token:
        monkeypatch.setenv("MT5_BRIDGE_TOKEN", token)
    if url:
        monkeypatch.setenv("MT5_BRIDGE_URL", url)
    module = importlib.import_module("src.live.mt5_api_connector")
    return importlib.reload(module)


def test_request_terminal_demand_posts_to_the_bridge_with_the_token(monkeypatch):
    module = _api_connector(monkeypatch)
    seen = {}
    _install_fake_httpx(monkeypatch, module, seen)

    assert module.request_terminal_demand() is True

    assert seen["posts"] == [("http://127.0.0.1:8081/api/terminal/demand", {"X-Bridge-Token": "s3cret"})]


def test_request_terminal_demand_reports_a_rejected_lease(monkeypatch):
    module = _api_connector(monkeypatch)
    seen = {}
    _install_fake_httpx(monkeypatch, module, seen, status_code=401)

    assert module.request_terminal_demand() is False


def test_request_terminal_demand_survives_an_unreachable_bridge(monkeypatch):
    module = _api_connector(monkeypatch)
    seen = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            raise OSError("bridge unreachable")

    monkeypatch.setattr(module.httpx, "Client", FakeClient)

    assert module.request_terminal_demand() is False
    assert seen == {}


def test_open_session_renews_the_lease_and_stops_when_it_closes(monkeypatch, services):
    posts = []
    monkeypatch.setattr(services, "_send_terminal_demand", lambda: posts.append(1))
    monkeypatch.setattr(services, "terminal_demand_renew_seconds", lambda: 0.01)

    async def scenario():
        services.register_connection()
        await asyncio.sleep(0.06)
        assert posts, "an open session must renew the lease"
        services.unregister_connection()
        await asyncio.sleep(0.02)
        after_close = len(posts)
        await asyncio.sleep(0.06)
        assert len(posts) == after_close, "a closed session must stop renewing"

    asyncio.run(scenario())


def test_second_session_does_not_start_a_second_renewal_loop(monkeypatch, services):
    posts = []
    monkeypatch.setattr(services, "_send_terminal_demand", lambda: posts.append(1))
    monkeypatch.setattr(services, "terminal_demand_renew_seconds", lambda: 0.05)

    async def scenario():
        services.register_connection()
        first_task = services._demand_task
        services.register_connection()

        assert services._demand_task is first_task

        services.unregister_connection()
        services.unregister_connection()

    asyncio.run(scenario())


def test_no_renewal_without_an_open_session(monkeypatch, services):
    posts = []
    monkeypatch.setattr(services, "_send_terminal_demand", lambda: posts.append(1))
    monkeypatch.setattr(services, "terminal_demand_renew_seconds", lambda: 0.01)

    async def scenario():
        await asyncio.sleep(0.05)
        assert posts == []
        assert services._demand_task is None

    asyncio.run(scenario())


def test_renewal_is_skipped_for_a_crypto_workspace(monkeypatch, services):
    class _Engine:
        _platform = "crypto"

    monkeypatch.setattr(services, "_market_data_engine", _Engine(), raising=False)
    posts = []
    monkeypatch.setattr(services, "_send_terminal_demand", lambda: posts.append(1))
    monkeypatch.setattr(services, "terminal_demand_renew_seconds", lambda: 0.01)

    async def scenario():
        services.register_connection()
        await asyncio.sleep(0.05)
        services.unregister_connection()
        assert posts == [], "a crypto workspace must never wake the MT5 terminal"

    asyncio.run(scenario())


@pytest.mark.parametrize("raw", ["", "0", "-3", "not-a-number"])
def test_renew_interval_falls_back_for_unusable_values(monkeypatch, services, raw):
    monkeypatch.setenv(services.TERMINAL_DEMAND_RENEW_ENV, raw)

    assert services.terminal_demand_renew_seconds() == services.DEFAULT_TERMINAL_DEMAND_RENEW


def test_renew_interval_reads_a_positive_value(monkeypatch, services):
    monkeypatch.setenv(services.TERMINAL_DEMAND_RENEW_ENV, "45")

    assert services.terminal_demand_renew_seconds() == 45.0


def test_release_terminal_demand_deletes_the_lease_with_the_token(monkeypatch):
    module = _api_connector(monkeypatch)
    seen = {}
    _install_fake_httpx(monkeypatch, module, seen)

    assert module.release_terminal_demand() is True

    assert seen["deletes"] == [
        ("http://127.0.0.1:8081/api/terminal/demand", {"X-Bridge-Token": "s3cret"})
    ]
    assert seen.get("posts") is None


def test_closing_the_last_session_releases_the_lease(monkeypatch, services):
    events = []
    monkeypatch.setattr(services, "_send_terminal_demand", lambda: events.append("renew"))
    monkeypatch.setattr(services, "_release_terminal_demand", lambda: events.append("release"))
    monkeypatch.setattr(services, "terminal_demand_renew_seconds", lambda: 0.01)

    async def scenario():
        services.register_connection()
        await asyncio.sleep(0.04)
        assert "renew" in events
        services.unregister_connection()
        await asyncio.sleep(0.05)
        assert events[-1] == "release", (
            "the bridge must stop being allowed to boot the terminal the moment the "
            "last session closes, not after the lease expires"
        )

    asyncio.run(scenario())


def test_release_never_runs_while_a_session_stays_open(monkeypatch, services):
    events = []
    monkeypatch.setattr(services, "_send_terminal_demand", lambda: events.append("renew"))
    monkeypatch.setattr(services, "_release_terminal_demand", lambda: events.append("release"))
    monkeypatch.setattr(services, "terminal_demand_renew_seconds", lambda: 0.01)

    async def scenario():
        services.register_connection()
        services.register_connection()
        services.unregister_connection()
        await asyncio.sleep(0.04)
        assert "release" not in events
        services.unregister_connection()

    asyncio.run(scenario())
