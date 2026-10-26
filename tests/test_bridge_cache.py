"""The in-process TTL cache that removes bridge round trips from polling paths.

Every request through the bridge costs ~418ms of transport, and two reads in
``src/platform/api/main.py`` ask it for data that barely changes: the deals
history (polled every 10s by the history panel) and symbol metadata such as
tick size and volume limits (read by the order path). The helper here holds
those answers in-process between reads.

It also has to be safe for trading data, so two rules are pinned below: a
``None`` result is never remembered (an unresolved symbol must be retried), and
a caller can refuse to cache a payload (an empty deals list is as likely to be
a bridge hiccup as an empty history).

This interpreter has no fastapi, so the routes that consume the helper cannot
be exercised here; these tests drive the helper itself through its public
interface.
"""

import ast
import threading
import time
from pathlib import Path

import pytest

from src.platform.api import deals_cache
from src.platform.api.deals_cache import cached


class _Clock:
    """Stand-in for the ``time`` module: only ``monotonic`` is used."""

    def __init__(self, start=1000.0):
        self.now = start

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = _Clock()
    monkeypatch.setattr(deals_cache, "time", fake)
    return fake


def test_hit_inside_ttl_does_not_call_the_producer(clock):
    cache = {}
    calls = []

    def producer():
        calls.append(clock.now)
        return {"volume_min": 0.01}

    first = cached(cache, "EURUSD", 300.0, producer)
    clock.advance(299.0)
    second = cached(cache, "EURUSD", 300.0, producer)

    assert first == {"volume_min": 0.01}
    assert second == {"volume_min": 0.01}
    assert len(calls) == 1, "a fresh entry must not pay a second producer call"


def test_expiry_calls_the_producer_again(clock):
    cache = {}
    calls = []

    def producer():
        calls.append(clock.now)
        return len(calls)

    assert cached(cache, "EURUSD", 300.0, producer) == 1
    clock.advance(300.0)
    assert cached(cache, "EURUSD", 300.0, producer) == 2
    clock.advance(299.0)
    assert cached(cache, "EURUSD", 300.0, producer) == 2
    clock.advance(1.0)
    assert cached(cache, "EURUSD", 300.0, producer) == 3


def test_ttl_is_measured_from_when_the_producer_finished(clock):
    """A slow producer must not arrive already expired."""
    cache = {}

    def slow_producer():
        clock.advance(20.0)
        return "rules"

    cached(cache, "NQ", 30.0, slow_producer)
    clock.advance(25.0)  # 45s after the call started, 25s after it answered
    assert cached(cache, "NQ", 30.0, lambda: "refetched") == "rules"


def test_none_result_is_never_cached(clock):
    cache = {}
    calls = []

    def producer():
        calls.append(clock.now)
        return None

    assert cached(cache, "UNRESOLVED", 300.0, producer) is None
    assert cached(cache, "UNRESOLVED", 300.0, producer) is None

    assert len(calls) == 2, "an unresolved symbol must be retried"
    assert cache == {}, "a None result must not occupy the cache"


def test_uncacheable_result_is_returned_but_not_stored(clock):
    cache = {}
    calls = []
    is_cacheable = lambda value: bool(value)  # noqa: E731 - mirrors the deals rule

    def producer():
        calls.append(clock.now)
        return []

    assert cached(cache, "deals", 30.0, producer, cacheable=is_cacheable) == []
    assert cached(cache, "deals", 30.0, producer, cacheable=is_cacheable) == []

    assert len(calls) == 2
    assert cache == {}


def test_cacheable_result_is_stored(clock):
    cache = {}
    calls = []

    def producer():
        calls.append(clock.now)
        return [{"ticket": 1}]

    assert cached(cache, "deals", 30.0, producer, cacheable=lambda v: bool(v)) == [
        {"ticket": 1}
    ]
    clock.advance(10.0)
    assert cached(cache, "deals", 30.0, producer, cacheable=lambda v: bool(v)) == [
        {"ticket": 1}
    ]
    assert len(calls) == 1


def test_separate_keys_do_not_collide(clock):
    cache = {}

    assert cached(cache, "EURUSD", 300.0, lambda: "eurusd") == "eurusd"
    assert cached(cache, "NQ", 300.0, lambda: "nq") == "nq"
    assert cached(cache, ("deals", "mt5", 365, None), 30.0, lambda: "deals") == "deals"

    assert cached(cache, "EURUSD", 300.0, lambda: "wrong") == "eurusd"
    assert cached(cache, "NQ", 300.0, lambda: "wrong") == "nq"
    assert (
        cached(cache, ("deals", "mt5", 365, None), 30.0, lambda: "wrong") == "deals"
    )
    assert len(cache) == 3


def test_zero_ttl_always_produces(clock):
    cache = {}
    calls = []

    def producer():
        calls.append(clock.now)
        return "fresh"

    cached(cache, "key", 0.0, producer)
    cached(cache, "key", 0.0, producer)

    assert len(calls) == 2


def test_concurrent_callers_on_one_key_share_a_single_producer_call():
    cache = {}
    calls = []
    results = []
    barrier = threading.Barrier(8)

    def producer():
        calls.append(threading.current_thread().name)
        time.sleep(0.02)
        return "rules"

    def worker():
        barrier.wait()
        results.append(cached(cache, "EURUSD", 300.0, producer))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5.0)

    assert not any(thread.is_alive() for thread in threads)
    assert len(results) == 8
    assert len(calls) == 1, "waiters must not repeat the producer work"
    assert set(results) == {"rules"}
    assert cache["EURUSD"]["value"] == "rules"


def test_concurrent_callers_on_separate_keys_keep_their_own_values():
    cache = {}
    keys = ["EURUSD", "NQ", "ES", "BTCUSD", "ETHUSD"]
    lock = threading.Lock()
    produced = {}
    failures = []
    barrier = threading.Barrier(len(keys) * 4)

    def make_producer(key):
        def producer():
            with lock:
                produced[key] = produced.get(key, 0) + 1
            time.sleep(0.01)
            return f"{key}-rules"

        return producer

    def worker(key):
        try:
            barrier.wait()
            value = cached(cache, key, 300.0, make_producer(key))
            if value != f"{key}-rules":
                with lock:
                    failures.append((key, value))
        except Exception as exc:  # pragma: no cover - reported through failures
            with lock:
                failures.append((key, exc))

    threads = [
        threading.Thread(target=worker, args=(key,)) for key in keys for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5.0)

    assert not any(thread.is_alive() for thread in threads)
    assert failures == []
    assert produced == {key: 1 for key in keys}
    assert {key: entry["value"] for key, entry in cache.items()} == {
        key: f"{key}-rules" for key in keys
    }


def test_on_hit_reports_only_cache_hits(clock):
    cache = {}
    hits = []

    def producer():
        return "rules"

    cached(cache, "EURUSD", 300.0, producer, on_hit=lambda: hits.append("hit"))
    assert hits == []

    clock.advance(1.0)
    cached(cache, "EURUSD", 300.0, producer, on_hit=lambda: hits.append("hit"))
    assert hits == ["hit"]

    clock.advance(300.0)
    cached(cache, "EURUSD", 300.0, producer, on_hit=lambda: hits.append("hit"))
    assert hits == ["hit"], "an expired entry is not a hit"


MAIN = Path(__file__).resolve().parents[1] / "src/platform/api/main.py"


def _batch_ticks_section():
    """The tape half of ``get_realtime_batch``: ticks, not account state."""
    source = MAIN.read_text()
    tree = ast.parse(source)
    handler = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_realtime_batch"
    )
    lines = source.splitlines()[handler.lineno - 1 : handler.end_lineno]
    start = next(
        index
        for index, line in enumerate(lines)
        if line.strip().startswith("# 2. Fetch Ticks")
    )
    return "\n".join(lines), "\n".join(lines[start:])


def test_the_tape_never_reads_the_ttl_cache():
    """Freshness of the tape is ticks-only, so caching must stay off that path."""
    handler, ticks = _batch_ticks_section()

    assert "cached(" not in ticks, "the ticks path must not be served from a cache"
    assert "_symbol_info_cache" not in ticks
    assert "get_recent_ticks" in ticks, "the tick source must still be the connector"

    account_ttl = [
        line for line in handler.splitlines() if line.strip().startswith("acc_ttl")
    ]
    assert account_ttl == ['    acc_ttl = 5.0 if target_platform == "crypto" else 3.0']

    throttle = [line for line in handler.splitlines() if "global throttle" in line]
    assert len(throttle) == 1
    assert "< 1.0" in throttle[0], "the 1.0s batch throttle must stay as it was"
