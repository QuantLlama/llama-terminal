"""Tiny dependency-free TTL cache for bridge reads in the API layer.

Each request through the MT5 bridge costs roughly 418ms of transport (the
container reaches the bridge through a socat relay over a tailnet with a ~189ms
round trip, paid twice), so the API layer must not ask the bridge again for an
answer that barely changes. Two reads in ``src/platform/api/main.py`` use this
helper:

* ``/api/deals`` -- the history panel polls every 10s and the underlying history
  shrinks or grows by a row at a time.
* symbol metadata (tick size, digits, volume min/max/step) -- effectively
  static, and read on the order path before an order is sent.

The helper is deliberately small and imports only ``threading`` and ``time`` so
it can be tested without fastapi/pydantic, neither of which exists in every
interpreter that runs the suite.

Contract
--------
``cached(cache, key, ttl, producer)`` returns ``cache[key]`` when the entry is
younger than ``ttl`` seconds; otherwise it calls ``producer()``, stores the
answer and returns it.

Two rules make it safe for trading data:

* ``None`` is never stored, so a symbol or history the bridge failed to resolve
  is retried on the next call instead of being remembered as "unknown".
* ``cacheable`` lets the caller refuse to store a payload that is technically
  not ``None`` but still worthless as a memory, such as an empty deals list --
  an empty list is as likely to be a bridge hiccup as an empty history.

Freshness is measured with ``time.monotonic()`` from the moment the producer
answered, so a slow call does not arrive already expired, and a wall-clock
jump cannot make entries immortal.

Concurrency
-----------
A ``cache`` is a plain dict of module-level lifetime; the helper owns one lock
per cache and computes the producer while holding it, so concurrent callers for
the same key pay one bridge round trip instead of one each. That also means the
producer must not re-enter the same cache from inside its own call, and it
should stay short: other keys on that cache wait behind it.
"""

import threading
import time
from typing import Any, Callable, Dict, Optional

# One lock per cache dict, so two caches never block each other. Keyed by the
# identity of the caller's module-level dict; entries live for the process
# lifetime, exactly like the caches they guard.
_cache_locks: Dict[int, threading.Lock] = {}
_cache_locks_guard = threading.Lock()


def _lock_for(cache: Dict[Any, Any]) -> threading.Lock:
    """The lock that guards ``cache``, created on first use."""
    with _cache_locks_guard:
        lock = _cache_locks.get(id(cache))
        if lock is None:
            lock = threading.Lock()
            _cache_locks[id(cache)] = lock
        return lock


def cached(
    cache: Dict[Any, Any],
    key: Any,
    ttl: float,
    producer: Callable[[], Any],
    *,
    cacheable: Optional[Callable[[Any], bool]] = None,
    on_hit: Optional[Callable[[], None]] = None,
) -> Any:
    """``cache[key]`` when it is younger than ``ttl``, else ``producer()``.

    ``cacheable`` is consulted only for values that are not ``None``; a ``None``
    answer is returned without being stored whatever ``cacheable`` says.
    ``on_hit`` runs when the answer comes from the cache, which is how callers
    make the saved round trip visible in the logs.
    """
    lock = _lock_for(cache)
    with lock:
        entry = cache.get(key)
        if entry is not None and (time.monotonic() - entry["ts"]) < ttl:
            if on_hit is not None:
                on_hit()
            return entry["value"]

        value = producer()
        if value is None:
            return None
        if cacheable is not None and not cacheable(value):
            return value
        cache[key] = {"value": value, "ts": time.monotonic()}
        return value

def deals_as_dicts(rows):
    """Return deal rows as plain dicts.

    The MT5 path hands back namedtuples, and JSON serialises a namedtuple as an
    ARRAY: the browser then reads d.time and gets undefined, so every client-side
    filter silently drops every deal. The backend never noticed because it reads
    the same rows through getattr. Converting here keeps the wire format honest.
    """
    if not rows:
        return []
    result = []
    for row in rows:
        if isinstance(row, dict):
            result.append(row)
        elif hasattr(row, "_asdict"):
            result.append(dict(row._asdict()))
        elif hasattr(row, "__dict__"):
            result.append(dict(vars(row)))
        else:
            result.append(row)
    return result
