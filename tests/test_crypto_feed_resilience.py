"""Crypto feed resilience: adaptive cadence and recovery from a dead connector.

Specs S2 and S5 of ``odd/tasks/crypto-tape-dom-live.md``. Measured reality: one
request through the deployment's egress relay costs ~0.53 s, while the crypto feed
loop used a fixed 80 ms cadence and the poll allows a ticker every second, trades
every two and a book every one to three per symbol. The loop could never finish a
cycle, so the tape lagged and the socket starved. And because the public connector
returns empty structures instead of raising, a dead connector stayed invisible
with ``status ONLINE`` and the DOM stayed blank.

Everything here is observed through the engine's public surface: the cadence
function, the loop's measured sleeps, the engine buffers, its metrics and its
logs.
"""
import logging
import sys
import types

import pytest

from src.services import active_tenant
from src.services.market_data_engine import engine as engine_module

PERP = "BTC/USDT:USDT"
TICK_MS = 1_700_000_000_000


# ── fixtures ───────────────────────────────────────────────────────


class _Feed:
    """Mutable state of the stubbed exchange: healthy or completely empty."""

    def __init__(self, healthy=True):
        self.healthy = healthy
        self.ticker_calls = 0
        self.trade_calls = 0
        self.book_calls = 0


def _install_ccxt(monkeypatch, feed):
    """Stub ``ccxt`` with one perpetual market whose data the test controls."""
    created = []

    class _Exchange:
        def __init__(self, config):
            self.config = config
            self.markets = {
                PERP: {"symbol": PERP, "type": "swap", "linear": True,
                       "settle": "USDT"},
            }
            created.append(self)

        def load_markets(self):
            return self.markets

        def fetch_ticker(self, symbol):
            feed.ticker_calls += 1
            return {
                "symbol": symbol,
                "bid": 100.5,
                "ask": 100.7,
                "last": 100.6 if feed.healthy else 0.0,
                "baseVolume": 1.0,
                "quoteVolume": 100.6,
                "timestamp": TICK_MS,
            }

        def fetch_trades(self, symbol, limit=None):
            feed.trade_calls += 1
            if not feed.healthy:
                return []
            return [{"id": f"t{feed.trade_calls}", "timestamp": TICK_MS,
                     "price": 100.6, "amount": 0.5, "side": "buy"}]

        def fetch_order_book(self, symbol, limit=None):
            feed.book_calls += 1
            if not feed.healthy:
                return {"bids": [], "asks": [], "timestamp": TICK_MS}
            return {"bids": [[100.5, 1.5]], "asks": [[100.7, 1.25]],
                    "timestamp": TICK_MS}

        def fetch_ohlcv(self, symbol, timeframe="1m", since=None, limit=None):
            return [[TICK_MS, 100.0, 101.0, 99.5, 100.6, 42.0]]

    module = types.ModuleType("ccxt")
    module.binanceusdm = _Exchange
    monkeypatch.setitem(sys.modules, "ccxt", module)
    return created


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    monkeypatch.delenv("CRYPTO_HTTP_PROXY", raising=False)
    monkeypatch.delenv("CRYPTO_PUBLIC_EXCHANGE", raising=False)
    from src.live import crypto_public_connector as public_module

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


@pytest.fixture
def public_resets(monkeypatch):
    """Record calls to ``reset_public_data_connector`` instead of running them."""
    calls = []
    monkeypatch.setattr(
        "src.live.crypto_public_connector.reset_public_data_connector",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    return calls


def _poll_cycle(engine, symbol=PERP):
    """One poll with the time based gates reset, which stands for elapsed time."""
    engine._last_crypto_ticker_poll.clear()
    engine._last_crypto_trade_poll.clear()
    engine._last_crypto_book_poll_strict.clear()
    engine._last_crypto_candle_poll.clear()
    engine._poll_crypto_symbol(symbol, symbol)


# ── the cadence function ───────────────────────────────────────────


def test_cadence_grows_when_the_cycle_overruns_the_interval():
    grown = engine_module.next_crypto_poll_interval(80, 530, 1)

    assert grown > 80
    assert grown <= engine_module.CRYPTO_POLL_MAX_MS


def test_cadence_shrinks_when_the_cycle_is_far_below_the_interval():
    shrunk = engine_module.next_crypto_poll_interval(1000, 5, 1)

    assert shrunk < 1000
    assert shrunk >= engine_module.CRYPTO_POLL_MIN_MS


def test_cadence_keeps_an_interval_that_matches_the_cycle():
    assert engine_module.next_crypto_poll_interval(300, 300, 1) == 300


def test_cadence_never_leaves_its_bounds():
    for symbols in (1, 2, 7, 30):
        floor = engine_module.crypto_poll_floor_ms(symbols)
        for current_ms in (0, 1, 80, 250, 999, 5000):
            for cycle_ms in (0, 40, 80, 400, 2000, 60000):
                nxt = engine_module.next_crypto_poll_interval(
                    current_ms, cycle_ms, symbols
                )
                assert floor <= nxt <= engine_module.CRYPTO_POLL_MAX_MS


def test_cadence_floor_rises_with_the_number_of_symbols():
    floors = [
        engine_module.crypto_poll_floor_ms(symbols) for symbols in (1, 2, 5, 30)
    ]

    assert floors[0] == engine_module.CRYPTO_POLL_MIN_MS
    assert floors == sorted(floors)
    assert floors[-1] == engine_module.CRYPTO_POLL_MAX_MS
    assert engine_module.crypto_poll_floor_ms(5) > engine_module.crypto_poll_floor_ms(1)


def test_cadence_shrink_respects_the_multi_symbol_floor():
    floor = engine_module.crypto_poll_floor_ms(5)

    assert engine_module.next_crypto_poll_interval(floor, 0, 5) == floor
    assert engine_module.next_crypto_poll_interval(floor * 1.2, 1, 5) == floor


# ── the loop uses the computed interval and keeps no backlog ───────


class _FakeClock:
    """A clock the test advances, so a measured cycle is deterministic."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(round(seconds, 4))
        self.now += seconds

    def advance_ms(self, milliseconds):
        self.now += milliseconds / 1000.0


class _StopAfter:
    def __init__(self, iterations):
        self.remaining = iterations

    def is_set(self):
        if self.remaining <= 0:
            return True
        self.remaining -= 1
        return False


def test_crypto_loop_adapts_its_cadence_instead_of_accumulating_a_backlog(
    monkeypatch, engine
):
    clock = _FakeClock()
    monkeypatch.setattr(engine_module, "time", clock)
    engine._symbols = {PERP}
    engine._should_stop = _StopAfter(4)
    durations = iter([530.0, 10.0, 10.0, 10.0])

    def _scripted_poll(symbol):
        clock.advance_ms(next(durations))

    monkeypatch.setattr(engine, "_poll_symbol", _scripted_poll)

    engine._crypto_feed_loop()

    # A 530 ms cycle against the 80 ms floor never sleeps (no backlog piles up),
    # then the interval halves while the cycles stay cheap, down to the floor.
    assert clock.sleeps == [0.255, 0.1225, 0.07]


# ── recovery from a connector that returns nothing ─────────────────


def test_three_empty_cycles_drop_the_connector_and_reset_the_public_one(
    monkeypatch, engine, public_resets, caplog
):
    _install_ccxt(monkeypatch, _Feed(healthy=False))
    from src.live import crypto_public_connector as public_module

    with caplog.at_level(logging.WARNING):
        _poll_cycle(engine)
        _poll_cycle(engine)
        assert engine._crypto_connector_cache[PERP] is (
            public_module.get_public_data_connector()
        ), "the failing connector is cached while it is still being retried"
        assert public_resets == []
        _poll_cycle(engine)

    assert PERP not in engine._crypto_connector_cache
    assert len(public_resets) == 1
    assert public_resets[0] == ((), {})
    assert engine.metrics.errors_count == 1

    warnings = [
        record for record in caplog.records
        if record.levelno == logging.WARNING and PERP in record.getMessage()
    ]
    assert len(warnings) == 1, "one WARNING per dropped connector"
    assert "ticker last <= 0" in warnings[0].getMessage()


def test_the_dropped_symbol_starts_over_on_the_next_cycle(monkeypatch, engine):
    feed = _Feed(healthy=False)
    _install_ccxt(monkeypatch, feed)
    monkeypatch.setattr(
        "src.live.crypto_public_connector.reset_public_data_connector",
        lambda *args, **kwargs: None,
    )

    for _ in range(3):
        _poll_cycle(engine)
    assert PERP not in engine._crypto_connector_cache

    _poll_cycle(engine)

    assert feed.ticker_calls >= 4, "the feed keeps trying after dropping"
    assert PERP in engine._crypto_connector_cache
    assert engine.metrics.errors_count == 1


def test_a_healthy_cycle_resets_the_failure_counter(
    monkeypatch, engine, public_resets
):
    feed = _Feed(healthy=False)
    _install_ccxt(monkeypatch, feed)

    _poll_cycle(engine)
    _poll_cycle(engine)
    feed.healthy = True
    _poll_cycle(engine)
    feed.healthy = False
    _poll_cycle(engine)
    _poll_cycle(engine)

    assert PERP in engine._crypto_connector_cache
    assert public_resets == []
    assert engine.metrics.errors_count == 0


def test_a_healthy_public_cycle_keeps_the_connector_and_serves_the_feed(
    monkeypatch, engine, public_resets
):
    _install_ccxt(monkeypatch, _Feed())
    from src.live import crypto_public_connector as public_module

    _poll_cycle(engine)

    assert engine._crypto_connector_cache[PERP] is (
        public_module.get_public_data_connector()
    )
    assert [t["price"] for t in engine.get_recent_trades(PERP)] == [100.6]
    assert engine.get_book_snapshot(PERP)["bids"][0]["price"] == 100.5
    assert public_resets == []
    assert engine.metrics.errors_count == 0


def test_the_public_fallback_never_touches_the_account_manager(
    monkeypatch, engine, public_resets
):
    _install_ccxt(monkeypatch, _Feed(healthy=False))
    manager_calls = []
    monkeypatch.setattr(
        "src.services.crypto_manager.get_crypto_manager",
        lambda: manager_calls.append("called"),
    )

    for _ in range(3):
        _poll_cycle(engine)

    assert manager_calls == []
    assert engine.metrics.errors_count == 1


# ── the account path is untouched ──────────────────────────────────


class _AccountConnector:
    """Healthy account-credentialed connector; records what the feed asked."""

    def __init__(self):
        self.connected = False
        self.trade_calls = 0

    def connect(self):
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
        self.trade_calls += 1
        return [{"timestamp": 1_700_000_001.0, "price": 200.6, "amount": 1.0,
                 "side": "BUY", "id": f"account-{self.trade_calls}"}]

    def get_book_snapshot(self, symbol, limit=20):
        return {"bids": [{"price": 200.5, "size": 1.0}],
                "asks": [{"price": 200.7, "size": 1.0}],
                "timestamp": 1_700_000_001.0}

    def get_ohlcv(self, symbol, timeframe="1m", limit=100):
        return []


def test_the_account_path_is_untouched_with_an_active_tenant(
    monkeypatch, engine, public_resets
):
    created = _install_ccxt(monkeypatch, _Feed())
    account_connector = _AccountConnector()
    manager_calls = []

    class Manager:
        def get_accounts(self, *, user_id):
            manager_calls.append(user_id)
            return [{"id": "c1", "is_master": True}]

    monkeypatch.setattr(
        "src.services.crypto_manager.get_crypto_manager", lambda: Manager()
    )
    module = types.ModuleType("src.live.crypto_connector")
    module.get_connector = lambda account_id, *, user_id: account_connector
    monkeypatch.setitem(sys.modules, "src.live.crypto_connector", module)

    active_tenant.set_active_user_id("user-b")
    for _ in range(4):
        _poll_cycle(engine)

    assert manager_calls and set(manager_calls) == {"user-b"}
    assert "crypto_public" not in engine._connectors
    assert public_resets == []
    assert created == [], "the public exchange is never built for a tenant"
    assert engine.metrics.errors_count == 0
    prices = [t["price"] for t in engine.get_recent_trades(PERP)]
    assert prices and set(prices) == {200.6}


def test_the_account_connector_keeps_requiring_a_tenant(monkeypatch, engine):
    _install_ccxt(monkeypatch, _Feed())
    manager_calls = []
    monkeypatch.setattr(
        "src.services.crypto_manager.get_crypto_manager",
        lambda: manager_calls.append("called"),
    )

    assert engine._get_connector("crypto") is None
    assert manager_calls == []


def test_a_ticker_only_cycle_still_counts_as_an_attempt(
    engine, monkeypatch, public_resets, caplog
):
    """The ticker is the primary signal, so a cycle where trades and the book are
    rate-limited must still judge the connector instead of staying neutral."""
    feed = _Feed(healthy=False)
    _install_ccxt(monkeypatch, feed)
    engine.subscribe([PERP])

    with caplog.at_level(logging.WARNING):
        for _ in range(engine_module.CRYPTO_FAILURE_LIMIT):
            engine._last_crypto_ticker_poll.clear()
            # Hold the other two requests inside their own rate limit for this cycle.
            engine._last_crypto_trade_poll[PERP.upper()] = engine_module.time.time()
            engine._last_crypto_book_poll_strict[PERP.upper()] = engine_module.time.time()
            engine._poll_crypto_symbol(PERP, PERP)

    assert feed.ticker_calls >= engine_module.CRYPTO_FAILURE_LIMIT
    assert feed.trade_calls == 0, "trades were rate-limited; the ticker must decide"
    assert PERP.upper() not in engine._crypto_connector_cache
    assert engine._metrics.errors_count == 1
    assert public_resets, "the failing public connector must be reset"
    assert "Dropped crypto connector" in caplog.text
