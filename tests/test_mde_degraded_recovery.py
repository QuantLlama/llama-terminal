"""A degraded market-data feed must be able to recover on its own.

``_feed_loop`` only reconnected while the status was ``OFFLINE`` or
``RECONNECTING``, but a transient poll exception moves an ``ONLINE`` feed to
``DEGRADED`` and nothing ever set ``OFFLINE`` again. A single hiccup therefore
parked the feed in ``DEGRADED`` until the process restarted: production
``/health`` reported ``market_data: DEGRADED`` for minutes while the bridge
answered every poll with 200.

The loop is driven iteration by iteration (``_should_stop`` becomes set after a
fixed number of checks) and the engine module's ``time`` is a deterministic
clock, so no feed thread starts and nothing sleeps for real.
"""
import time as time_module

import pytest

from src.services.market_data_engine import engine as engine_module
from src.services.market_data_engine.models import FeedStatus


class _FakeClock:
    """Deterministic stand-in for the ``time`` name imported by the engine.

    ``time()`` never moves on its own; the loop's own ``sleep`` advances it, so
    the throttle sees exactly the elapsed time the loop believes in.
    """

    def __init__(self, start=1000.0, tick=0.05):
        self.now = float(start)
        self.tick = float(tick)
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += max(float(seconds), self.tick)


class _StopAfter:
    """``_should_stop`` that stays clear for ``iterations`` loop checks."""

    def __init__(self, iterations):
        self._remaining = int(iterations)

    def is_set(self):
        if self._remaining <= 0:
            return True
        self._remaining -= 1
        return False


class _FakeMT5Connector:
    """Records every ``connect`` call and answers with the scripted results."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def connect(self, **kwargs):
        self.calls.append(kwargs)
        return self._results.pop(0) if self._results else False


@pytest.fixture
def engine(monkeypatch):
    """A real engine instance, with the singleton reset and its log handler undone."""
    module_logger = engine_module.logger
    handlers_before = list(module_logger.handlers)
    monkeypatch.setattr(engine_module.MarketDataEngine, "_instance", None)

    instance = engine_module.MarketDataEngine(platform="mt5")

    yield instance

    for handler in module_logger.handlers[:]:
        if handler not in handlers_before:
            module_logger.removeHandler(handler)
            handler.close()


@pytest.fixture
def clock(monkeypatch):
    """Replace the engine module's clock and make ``time.sleep`` a no-op."""
    fake = _FakeClock()
    monkeypatch.setattr(time_module, "sleep", lambda *args, **kwargs: None)
    monkeypatch.setattr(engine_module, "time", fake)
    return fake


def test_degraded_feed_reconnects_and_returns_online(engine, clock):
    connector = _FakeMT5Connector([True])
    engine._connectors = {"mt5": connector}
    engine._reconnect_delay_s = 0
    engine._update_status(FeedStatus.DEGRADED)
    engine._should_stop = _StopAfter(1)

    engine._feed_loop()

    assert connector.calls == [{}]
    assert engine.status is FeedStatus.ONLINE


@pytest.mark.parametrize("status", [FeedStatus.OFFLINE, FeedStatus.RECONNECTING])
def test_existing_offline_recovery_path_still_works(engine, clock, status):
    """Preserve: the recovery states that already worked keep working."""
    connector = _FakeMT5Connector([True])
    engine._connectors = {"mt5": connector}
    engine._reconnect_delay_s = 0
    engine._update_status(status)
    engine._should_stop = _StopAfter(1)

    engine._feed_loop()

    assert connector.calls == [{}]
    assert engine.status is FeedStatus.ONLINE


def test_degraded_reconnect_attempts_are_throttled(engine, clock):
    connector = _FakeMT5Connector([False] * 5)
    engine._connectors = {"mt5": connector}
    engine._reconnect_delay_s = 300
    engine._update_status(FeedStatus.DEGRADED)
    engine._should_stop = _StopAfter(4)

    engine._feed_loop()

    assert len(connector.calls) == 1
    assert engine.status is FeedStatus.DEGRADED


def test_degraded_reconnect_resumes_once_the_delay_elapsed(engine, clock):
    clock.tick = 400.0
    connector = _FakeMT5Connector([False] * 5)
    engine._connectors = {"mt5": connector}
    engine._reconnect_delay_s = 300
    engine._update_status(FeedStatus.DEGRADED)
    engine._should_stop = _StopAfter(2)

    engine._feed_loop()

    assert len(connector.calls) == 2
    assert engine.status is FeedStatus.DEGRADED


def test_failed_reconnect_from_degraded_keeps_the_feed_usable(engine, clock):
    connector = _FakeMT5Connector([False] * 10)
    engine._connectors = {"mt5": connector}
    engine._reconnect_delay_s = 0
    engine._max_reconnect_attempts = 3

    seen = []
    engine._status_callbacks.append(seen.append)
    engine._update_status(FeedStatus.DEGRADED)
    engine._should_stop = _StopAfter(4)

    engine._feed_loop()

    assert len(connector.calls) == 3
    assert engine.status is FeedStatus.DEGRADED
    assert engine.is_online is True
    assert FeedStatus.OFFLINE not in seen


class _RaisingConnector:
    """A connector whose ``connect`` raises, like a bridge that is down."""

    def __init__(self):
        self.calls = 0

    def connect(self, **kwargs):
        self.calls += 1
        raise RuntimeError("bridge unreachable")


def test_a_raising_reconnect_is_logged_and_leaves_the_feed_usable(engine, clock, caplog):
    """The swallowed exception used to leave DEGRADED with no trace at all.

    Making DEGRADED retry turns this path from rare into routine, so the failure
    has to be visible in the log rather than inferred from the status bouncing.
    """
    connector = _RaisingConnector()
    engine._connectors = {"mt5": connector}
    engine._reconnect_delay_s = 0
    engine._update_status(FeedStatus.DEGRADED)
    engine._should_stop = _StopAfter(2)

    with caplog.at_level("WARNING", logger=engine_module.logger.name):
        engine._feed_loop()

    assert connector.calls >= 1
    assert engine.status is FeedStatus.DEGRADED
    assert engine.is_online is True
    assert any(
        "bridge unreachable" in record.getMessage() for record in caplog.records
    ), [record.getMessage() for record in caplog.records]
