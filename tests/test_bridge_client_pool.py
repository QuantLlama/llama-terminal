"""One pooled ``httpx.Client`` per connector instance (bridge latency).

Every ``with self._bridge_client() as client:`` call site used to build a brand
new ``httpx.Client``, so each request paid a full TCP handshake through the
socat relay and the tailnet tunnel on every polling cycle. The connector must
reuse a single shared client instead, applied per request for the one call site
that asks for ``timeout=90.0``.

``httpx`` is not installed in every interpreter that runs this suite, so a
minimal stand-in module is registered when the real one is missing. No test
performs a network request: ``httpx.Client`` is always replaced before the
shared client is created.
"""

import sys
import threading
import time
import types

import pytest


def _install_httpx_stub_if_missing():
    """Register a tiny ``httpx`` stand-in so the connector module can import."""
    try:
        import httpx  # noqa: F401
    except ModuleNotFoundError:
        stub = types.ModuleType("httpx")

        class _Timeout:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        class _Limits:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        class _Client:  # replaced per test; never used for real requests
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        stub.Timeout = _Timeout
        stub.Limits = _Limits
        stub.Client = _Client
        sys.modules["httpx"] = stub


_install_httpx_stub_if_missing()

from src.live.mt5_api_connector import MT5ApiConnector  # noqa: E402


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.status_code = status_code
        self._payload = {} if payload is None else payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")


class FakeHttpClient:
    """Records construction kwargs and every request it is asked to make."""

    instances = []
    create_delay = 0.0
    payload = {}

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.requests = []
        self.closed = False
        FakeHttpClient.instances.append(self)
        if FakeHttpClient.create_delay:
            import time

            time.sleep(FakeHttpClient.create_delay)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.closed = True
        return False

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        return FakeResponse(FakeHttpClient.payload)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def close(self):
        self.closed = True


@pytest.fixture
def connector(monkeypatch):
    """A connector whose pooled client is created lazily inside the test."""
    monkeypatch.setenv("MT5_AUTO_LAUNCH", "false")
    monkeypatch.delenv("MT5_BRIDGE_URL", raising=False)
    import src.live.mt5_api_connector as module

    monkeypatch.setattr(MT5ApiConnector, "_ensure_server_running", lambda self: None)
    MT5ApiConnector._instance = None
    FakeHttpClient.instances = []
    FakeHttpClient.create_delay = 0.0
    FakeHttpClient.payload = {}
    monkeypatch.setattr(module.httpx, "Client", FakeHttpClient)
    instance = MT5ApiConnector(base_url="http://127.0.0.1:9")
    # Building the connector also builds its own client; the pool under test is
    # the one created lazily on first bridge call.
    FakeHttpClient.instances = []
    yield instance
    MT5ApiConnector._instance = None
    FakeHttpClient.instances = []


def _pooled():
    pooled = [c for c in FakeHttpClient.instances if c.kwargs.get("base_url")]
    assert len(pooled) == 1, f"expected one pooled client, got {len(pooled)}"
    return pooled[0]


def test_two_uses_share_one_underlying_client(connector):
    with connector._bridge_client() as first:
        first.get("/api/positions")
    with connector._bridge_client() as second:
        second.get("/api/pending_orders")

    assert first._client is second._client
    assert len(FakeHttpClient.instances) == 1


def test_exit_does_not_close_the_shared_client(connector):
    with connector._bridge_client() as client:
        underlying = client._client
        assert underlying.closed is False

    assert underlying.closed is False, "closing on __exit__ defeats the pool"


def test_timeout_is_forwarded_per_request_not_to_the_client(connector):
    with connector._bridge_client(timeout=90.0) as client:
        client.get("/api/symbols")
    with connector._bridge_client(timeout=2.0) as client:
        client.get("/api/symbols")

    pooled = _pooled()
    assert pooled.kwargs.get("timeout") != 90.0, "the per-call timeout must not reach the client"
    assert [call[2]["timeout"] for call in pooled.requests] == [90.0, 2.0]


def test_calls_without_a_timeout_keep_the_client_default(connector):
    with connector._bridge_client() as client:
        client.get("/api/daily_pnl")

    assert "timeout" not in _pooled().requests[0][2]


def test_shared_client_is_created_once_under_concurrent_access(connector):
    FakeHttpClient.create_delay = 0.05
    created = []
    barrier = threading.Barrier(8)

    def use_bridge():
        barrier.wait()
        created.append(connector._bridge_client()._client)

    threads = [threading.Thread(target=use_bridge) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert len(FakeHttpClient.instances) == 1, "the lock must guard creation"
    assert len(created) == 8
    assert all(client is FakeHttpClient.instances[0] for client in created)


def test_close_releases_the_pool_and_it_is_rebuilt_on_demand(connector):
    with connector._bridge_client() as client:
        first = client._client

    connector.close()

    assert first.closed is True
    with connector._bridge_client() as client:
        second = client._client
    assert second is not first
    assert second.closed is False


# --- behaviour that must not change ----------------------------------------


def test_requests_still_carry_the_bridge_token(connector, monkeypatch):
    """The pooled client must keep the authenticated-header behaviour."""
    monkeypatch.setenv("MT5_BRIDGE_TOKEN", "s3cret")
    connector.close()

    with connector._bridge_client() as client:
        client.get("/api/positions")

    headers = _pooled().kwargs.get("headers") or {}
    assert headers.get("X-Bridge-Token") == "s3cret"


def test_symbols_get_returns_the_catalogue(connector):
    """The ``timeout=90.0`` call site keeps working through the proxy."""
    FakeHttpClient.payload = [{"name": "EURUSD"}]

    symbols = connector.symbols_get(pattern="EUR")

    assert symbols == [{"name": "EURUSD"}]
    pooled = _pooled()
    assert pooled.requests[0][2]["params"] == {"pattern": "EUR"}
    assert pooled.requests[0][2]["timeout"] == 90.0


class FakeBridgeClient(FakeHttpClient):
    """A fake bridge: known paths answer, every other path answers 404.

    The real bridge is a FastAPI app, so a path it does not implement comes
    back as 404 from the router without MT5 being touched. ``delays`` per path
    lets a test decide which side of the round trip dominates.
    """

    statuses = {}
    delays = {}

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        delay = FakeBridgeClient.delays.get(url)
        if delay:
            time.sleep(delay)
        status = FakeBridgeClient.statuses.get(url, 404)
        payload = FakeHttpClient.payload if status == 200 else {"detail": "Not Found"}
        return FakeResponse(payload, status_code=status)


@pytest.fixture
def bridge(connector, monkeypatch):
    """The connector, pointed at a fake bridge with per-path status and delay."""
    import src.live.mt5_api_connector as module

    FakeBridgeClient.statuses = {"/api/balance": 200}
    FakeBridgeClient.delays = {}
    FakeHttpClient.payload = {"balance": 1000.0}
    monkeypatch.setattr(module.httpx, "Client", FakeBridgeClient)
    return connector


def _assert_latency_group(samples, min_ms, median_ms):
    """One reported group: three samples plus min/median, all rounded."""
    assert len(samples) == 3, samples
    assert all(isinstance(value, float) and value >= 0 for value in samples)
    assert isinstance(min_ms, float) and isinstance(median_ms, float)
    assert min_ms <= median_ms
    assert min_ms == min(samples)


def test_latency_probe_reports_the_transport_and_the_mt5_call_separately(bridge):
    """A 404 path measures the tunnel; /api/balance adds MT5 work on top of it."""
    FakeBridgeClient.delays = {"/api/balance": 0.02}

    result = bridge.probe_latency(count=3)

    pooled = _pooled()
    assert [call[1] for call in pooled.requests] == [
        "/api/balance"
    ] * 3 + ["/__probe__"] * 3
    _assert_latency_group(result["samples_ms"], result["min_ms"], result["median_ms"])
    _assert_latency_group(
        result["network_samples_ms"], result["network_min_ms"], result["network_median_ms"]
    )
    # 20 ms of extra far-side work dwarfs the (near-zero) fake transport.
    assert result["median_ms"] > result["network_median_ms"]
    assert result["interpretation"] == "mt5"


def test_latency_probe_calls_network_dominant_when_the_tunnel_is_slow(bridge):
    """``network_median_ms >= 50%`` of the full-call median means network."""
    FakeBridgeClient.delays = {"/__probe__": 0.02}

    result = bridge.probe_latency(count=3)

    assert result["network_median_ms"] >= 0.5 * result["median_ms"]
    assert result["interpretation"] == "network"


def test_latency_probe_still_uses_the_pooled_socket(bridge):
    """Both measurements ride the one shared client, not a fresh connection."""
    bridge.probe_latency(count=1)

    with bridge._bridge_client() as client:
        client.get("/api/positions")

    assert ["%s %s" % (call[0], call[1]) for call in _pooled().requests] == [
        "GET /api/balance",
        "GET /__probe__",
        "GET /api/positions",
    ]


def test_latency_probe_surfaces_a_dead_bridge(connector, monkeypatch):
    """A failing bridge must raise so the endpoint can report ``error``.

    ``/debug/bridge-latency`` catches this and still answers 200 with the
    ``error`` field set (``src/platform/api/main.py``, which needs fastapi and
    so is only byte-compiled here).
    """

    class DeadClient(FakeHttpClient):
        def request(self, method, url, **kwargs):
            raise RuntimeError("connect timeout")

    import src.live.mt5_api_connector as module

    monkeypatch.setattr(module.httpx, "Client", DeadClient)

    with pytest.raises(RuntimeError):
        connector.probe_latency(count=3)


def test_shutdown_does_not_close_the_pooled_client(connector):
    """`shutdown()` finishes most requests, so it must not tear down the pool.

    The connector's shutdown runs on every request that ends with a connector
    shutdown (platform switch, symbol refresh, /api/tick). Closing the shared
    client there would rebuild the connection — and pay the handshake through
    the relay again — on every cycle, and could close it under a concurrent
    request. Only an explicit close() may release the pool.
    """
    with connector._bridge_client() as client:
        underlying = client._client

    connector.shutdown()

    assert underlying.closed is False, (
        "shutdown() must not close the pooled client; it runs per request"
    )
    assert connector.connected is False
