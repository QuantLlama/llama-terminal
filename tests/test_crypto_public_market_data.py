"""Public crypto market data: the tape and the DOM without a trading tenant.

Specs S2 and S5 of ``odd/tasks/crypto-tape-dom-live.md``. The feed endpoints
(``/api/v2/feed/trades/*``, ``/api/v2/feed/dom/*``, ``/api/v2/feed/book/*`` and
``/api/v2/ws/feed``) are unauthenticated and read only from
:class:`MarketDataEngine`, so their data may not depend on an account
credentialed connector nor on an active trading tenant.

Everything here goes through the public interface: the module-level connector
cache, the connector's documented return contracts, and the engine's poll entry
point observed through ``get_recent_trades``/``get_book_snapshot``/metrics.
"""
import logging
import sys
import types

import pytest

from src.live import crypto_public_connector as public_module
from src.services import active_tenant
from src.services.market_data_engine import engine as engine_module

PERP = "BTC/USDT:USDT"
TICK_MS = 1_700_000_000_000


class _StubExchange:
    """A deterministic ccxt exchange: one perpetual market plus spot markets."""

    def __init__(self, exchange_id="binanceusdm", config=None):
        self.exchange_id = exchange_id
        self.config = dict(config or {})
        self.proxies = None
        self.markets = {
            PERP: {"symbol": PERP, "type": "swap", "linear": True, "settle": "USDT"},
            "BTC/USDT": {"symbol": "BTC/USDT", "type": "spot", "settle": "USDT"},
            "ETH/USDT": {"symbol": "ETH/USDT", "type": "spot", "settle": "USDT"},
        }
        self.load_markets_calls = 0
        self.calls = []

    def load_markets(self):
        self.load_markets_calls += 1
        self.calls.append(("load_markets",))
        return self.markets

    def fetch_ticker(self, symbol):
        self.calls.append(("fetch_ticker", symbol))
        return {
            "symbol": symbol,
            "bid": 100.5,
            "ask": 100.7,
            "last": 100.6,
            "baseVolume": 12.5,
            "quoteVolume": 1250.0,
            "timestamp": TICK_MS,
        }

    def fetch_trades(self, symbol, limit=None):
        self.calls.append(("fetch_trades", symbol, limit))
        return [
            {"id": "t1", "timestamp": TICK_MS + 1000, "price": 100.6,
             "amount": 0.5, "side": "buy"},
            {"id": "t2", "timestamp": TICK_MS + 2000, "price": 100.7,
             "amount": 0.25, "side": "sell"},
        ]

    def fetch_order_book(self, symbol, limit=None):
        self.calls.append(("fetch_order_book", symbol, limit))
        return {
            "bids": [[100.5, 1.5], [100.4, 2.0]],
            "asks": [[100.7, 1.25], [100.8, 3.0]],
            "timestamp": TICK_MS + 3000,
        }

    def fetch_ohlcv(self, symbol, timeframe="1m", since=None, limit=None):
        self.calls.append(("fetch_ohlcv", symbol, limit))
        return [[TICK_MS, 100.0, 101.0, 99.5, 100.6, 42.0]]


class _SpotOnlyExchange(_StubExchange):
    """An exchange where the requested asset only trades on the spot market."""

    def __init__(self, exchange_id="binanceusdm", config=None):
        super().__init__(exchange_id, config)
        self.markets = {
            "SOL/USDT": {"symbol": "SOL/USDT", "type": "spot", "settle": "USDT"},
        }


def _install_ccxt(monkeypatch, exchange_base=_StubExchange):
    """Stub ``ccxt`` so the connector builds a fake exchange we can inspect."""
    created = []

    def _factory(exchange_id):
        class _Exchange(exchange_base):
            def __init__(self, config):
                super().__init__(exchange_id, config)
                created.append(self)

        return _Exchange

    module = types.ModuleType("ccxt")
    for exchange_id in ("binanceusdm", "okx", "bybit"):
        setattr(module, exchange_id, _factory(exchange_id))
    monkeypatch.setitem(sys.modules, "ccxt", module)
    return created


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    monkeypatch.delenv("CRYPTO_HTTP_PROXY", raising=False)
    monkeypatch.delenv(public_module.EXCHANGE_ENV, raising=False)
    public_module.reset_public_data_connector()
    active_tenant.clear_active_user_id()
    yield
    public_module.reset_public_data_connector()
    active_tenant.clear_active_user_id()


@pytest.fixture
def engine(monkeypatch):
    """A real engine, without the log-directory side effect or the singleton."""
    monkeypatch.setattr(
        engine_module.MarketDataEngine, "_setup_logging", lambda self: None
    )
    engine_module.MarketDataEngine._instance = None
    instance = engine_module.MarketDataEngine(platform="crypto")
    instance._update_status(engine_module.FeedStatus.ONLINE)
    yield instance
    instance._executor.shutdown(wait=False)
    engine_module.MarketDataEngine._instance = None


# ── the connector cache ────────────────────────────────────────────


def test_public_connector_is_cached_per_exchange_id(monkeypatch):
    _install_ccxt(monkeypatch)

    first = public_module.get_public_data_connector("binanceusdm")
    assert public_module.get_public_data_connector("binanceusdm") is first

    other = public_module.get_public_data_connector("okx")
    assert other is not first
    assert public_module.get_public_data_connector("okx") is other
    assert other.exchange_id == "okx"

    public_module.reset_public_data_connector("okx")
    assert public_module.get_public_data_connector("okx") is not other


def test_default_exchange_comes_from_the_environment(monkeypatch):
    _install_ccxt(monkeypatch)

    assert public_module.get_public_data_connector().exchange_id == "binanceusdm"

    public_module.reset_public_data_connector()
    monkeypatch.setenv(public_module.EXCHANGE_ENV, "OKX")
    assert public_module.get_public_data_connector().exchange_id == "okx"


def test_public_connector_holds_no_credentials(monkeypatch):
    created = _install_ccxt(monkeypatch)

    connector = public_module.get_public_data_connector("binanceusdm")

    assert connector.connected is True
    exchange = created[0]
    assert exchange.load_markets_calls == 1
    assert "apiKey" not in exchange.config
    assert "secret" not in exchange.config
    assert "password" not in exchange.config
    assert exchange.config["options"]["defaultType"] == "swap"


def test_crypto_http_proxy_is_applied_to_the_public_exchange(monkeypatch):
    created = _install_ccxt(monkeypatch)
    monkeypatch.setenv("CRYPTO_HTTP_PROXY", "http://10.0.0.1:3128")

    public_module.get_public_data_connector("binanceusdm")

    assert created[0].proxies == {
        "http": "http://10.0.0.1:3128",
        "https": "http://10.0.0.1:3128",
    }


def test_no_proxy_leaves_the_public_exchange_alone(monkeypatch):
    created = _install_ccxt(monkeypatch)

    public_module.get_public_data_connector("binanceusdm")

    assert created[0].proxies is None


# ── symbol resolution ──────────────────────────────────────────────


def test_resolve_sym_prefers_the_perpetual_market(monkeypatch):
    _install_ccxt(monkeypatch)
    connector = public_module.get_public_data_connector("binanceusdm")

    assert connector._resolve_sym(PERP) == PERP
    assert connector._resolve_sym("BTC/USDT") == PERP
    assert connector._resolve_sym("btcusdt") == PERP


def test_resolve_sym_never_returns_a_spot_only_symbol(monkeypatch):
    _install_ccxt(monkeypatch, exchange_base=_SpotOnlyExchange)
    connector = public_module.get_public_data_connector("binanceusdm")

    assert connector._resolve_sym("SOL/USDT") is None


# ── return contracts (identical to src/live/crypto_connector.py) ───


def test_tick_matches_the_connector_contract(monkeypatch):
    created = _install_ccxt(monkeypatch)
    connector = public_module.get_public_data_connector("binanceusdm")

    tick = connector.get_tick(PERP)

    assert tick == {
        "symbol": PERP,
        "fetched_symbol": PERP,
        "exchange": "binanceusdm",
        "bid": 100.5,
        "ask": 100.7,
        "last": 100.6,
        "baseVolume": 12.5,
        "quoteVolume": 1250.0,
        "timestamp": TICK_MS,
        "time": 1_700_000_000.0,
    }
    assert ("fetch_ticker", PERP) in created[0].calls


def test_tick_resolves_the_symbol_before_fetching(monkeypatch):
    created = _install_ccxt(monkeypatch)
    connector = public_module.get_public_data_connector("binanceusdm")

    tick = connector.get_tick("BTC/USDT")

    assert tick["symbol"] == "BTC/USDT"
    assert tick["fetched_symbol"] == PERP
    assert ("fetch_ticker", PERP) in created[0].calls


def test_trades_match_the_connector_contract(monkeypatch):
    created = _install_ccxt(monkeypatch)
    connector = public_module.get_public_data_connector("binanceusdm")

    trades = connector.get_trades(PERP, limit=50)

    assert trades == [
        {"timestamp": 1_700_000_001.0, "price": 100.6, "amount": 0.5,
         "side": "BUY", "id": "t1"},
        {"timestamp": 1_700_000_002.0, "price": 100.7, "amount": 0.25,
         "side": "SELL", "id": "t2"},
    ]
    assert ("fetch_trades", PERP, 50) in created[0].calls


def test_trades_without_an_id_get_a_stable_one(monkeypatch):
    class _NoIdExchange(_StubExchange):
        def fetch_trades(self, symbol, limit=None):
            return [{"timestamp": TICK_MS + 1000, "price": 100.6,
                     "amount": 0.5, "side": "buy"}]

    _install_ccxt(monkeypatch, exchange_base=_NoIdExchange)
    connector = public_module.get_public_data_connector("binanceusdm")

    trades = connector.get_trades(PERP)

    assert trades[0]["id"] == "1700000001000_100.6_0.5"


def test_book_snapshot_matches_the_connector_contract(monkeypatch):
    created = _install_ccxt(monkeypatch)
    connector = public_module.get_public_data_connector("binanceusdm")

    book = connector.get_book_snapshot(PERP, limit=20)

    assert book == {
        "bids": [{"price": 100.5, "size": 1.5}, {"price": 100.4, "size": 2.0}],
        "asks": [{"price": 100.7, "size": 1.25}, {"price": 100.8, "size": 3.0}],
        "timestamp": 1_700_000_003.0,
    }
    assert ("fetch_order_book", PERP, 20) in created[0].calls


def test_book_snapshot_asks_for_a_limit_the_exchange_accepts(monkeypatch):
    created = _install_ccxt(monkeypatch)
    connector = public_module.get_public_data_connector("binanceusdm")

    connector.get_book_snapshot(PERP, limit=30)

    assert ("fetch_order_book", PERP, 50) in created[0].calls


# ── the engine without a trading tenant ────────────────────────────


def test_engine_serves_the_tape_and_the_dom_from_public_data_without_a_tenant(
    monkeypatch, engine
):
    _install_ccxt(monkeypatch)
    manager_calls = []
    monkeypatch.setattr(
        "src.services.crypto_manager.get_crypto_manager",
        lambda: manager_calls.append("called"),
    )

    engine._poll_crypto_symbol(PERP, PERP)

    trades = engine.get_recent_trades(PERP)
    assert [t["price"] for t in trades] == [100.6, 100.7]
    assert [t["side"] for t in trades] == ["BUY", "SELL"]

    book = engine.get_book_snapshot(PERP)
    assert book["bids"][0]["price"] == 100.5
    assert book["asks"][0]["price"] == 100.7

    assert engine.metrics.messages_received > 0
    assert manager_calls == [], "the public feed must not touch account state"
    assert engine._connectors["crypto_public"] is (
        public_module.get_public_data_connector()
    )


def test_engine_reads_the_public_feed_again_on_the_next_poll(monkeypatch, engine):
    created = _install_ccxt(monkeypatch)

    engine._poll_crypto_symbol(PERP, PERP)
    # The poll gates are time based; clearing them stands for the next window.
    engine._last_crypto_ticker_poll.clear()
    engine._last_crypto_trade_poll.clear()
    engine._last_crypto_book_poll_strict.clear()
    engine._poll_crypto_symbol(PERP, PERP)

    assert len(created) == 1, "one public exchange, reused across polls"
    exchange = created[0]
    assert exchange.load_markets_calls == 1, "markets are loaded once, not per poll"
    assert sum(1 for call in exchange.calls if call[0] == "fetch_ticker") == 2
    assert sum(1 for call in exchange.calls if call[0] == "fetch_trades") == 2
    assert len(engine.get_recent_trades(PERP)) == 2, "deduplicated, not duplicated"


# ── the engine with a trading tenant (unchanged account path) ──────


class _AccountConnector:
    """Account-credentialed connector stand-in; records what the feed asked."""

    def __init__(self):
        self.connected = False
        self.connect_calls = 0
        self.trade_calls = []

    def connect(self):
        self.connect_calls += 1
        self.connected = True
        return True

    def _resolve_sym(self, symbol):
        return PERP if symbol.upper().startswith("BTC") else None

    def get_tick(self, symbol):
        return {"symbol": symbol, "fetched_symbol": PERP,
                "exchange": "binanceusdm", "bid": 200.5, "ask": 200.7,
                "last": 200.6, "baseVolume": 1.0, "quoteVolume": 200.6,
                "timestamp": TICK_MS, "time": 1_700_000_000.0}

    def get_trades(self, symbol, limit=100):
        self.trade_calls.append((symbol, limit))
        return [{"timestamp": 1_700_000_001.0, "price": 200.6, "amount": 1.0,
                 "side": "BUY", "id": "account-1"}]

    def get_book_snapshot(self, symbol, limit=20):
        return {"bids": [{"price": 200.5, "size": 1.0}],
                "asks": [{"price": 200.7, "size": 1.0}],
                "timestamp": 1_700_000_001.0}

    def get_ohlcv(self, symbol, timeframe="1m", limit=100):
        return []


def _stub_account_path(monkeypatch, account_connector):
    manager_calls, connector_calls = [], []

    class Manager:
        def get_accounts(self, *, user_id):
            manager_calls.append(user_id)
            return [{"id": "c1", "is_master": True}]

    monkeypatch.setattr(
        "src.services.crypto_manager.get_crypto_manager", lambda: Manager()
    )
    module = types.ModuleType("src.live.crypto_connector")

    def _get_connector(account_id, *, user_id):
        connector_calls.append((account_id, user_id))
        return account_connector

    module.get_connector = _get_connector
    monkeypatch.setitem(sys.modules, "src.live.crypto_connector", module)
    return manager_calls, connector_calls


def test_engine_still_uses_the_account_connector_for_an_active_tenant(
    monkeypatch, engine
):
    created = _install_ccxt(monkeypatch)
    account_connector = _AccountConnector()
    manager_calls, connector_calls = _stub_account_path(monkeypatch, account_connector)

    active_tenant.set_active_user_id("user-b")
    engine._poll_crypto_symbol(PERP, PERP)

    # The master lookup and the per-account lookup both use the active tenant.
    assert manager_calls and set(manager_calls) == {"user-b"}
    assert connector_calls and set(connector_calls) == {("c1", "user-b")}
    assert account_connector.connect_calls == 1
    assert account_connector.trade_calls == [(PERP, 50)]
    assert [t["price"] for t in engine.get_recent_trades(PERP)] == [200.6]
    assert engine.get_book_snapshot(PERP)["bids"][0]["price"] == 200.5
    assert "crypto_public" not in engine._connectors
    assert created == [], "the public exchange must not be built for a tenant"


# ── preserved contract: the account connector still needs a tenant ──


def test_engine_still_logs_the_missing_tenant_once(monkeypatch, engine, caplog):
    """Operators grep this line to learn why account data is idle."""
    _install_ccxt(monkeypatch)

    with caplog.at_level(logging.WARNING):
        engine._poll_crypto_symbol(PERP, PERP)
        engine._poll_crypto_symbol(PERP, PERP)

    assert caplog.text.count(active_tenant.SKIP_MESSAGE) == 1
    assert "market-data-engine:crypto-poll" in caplog.text


def test_engine_account_connector_stays_none_without_a_tenant(monkeypatch, engine):
    _install_ccxt(monkeypatch)
    manager_calls = []
    monkeypatch.setattr(
        "src.services.crypto_manager.get_crypto_manager",
        lambda: manager_calls.append("called"),
    )

    assert engine._get_connector("crypto") is None
    assert manager_calls == []
