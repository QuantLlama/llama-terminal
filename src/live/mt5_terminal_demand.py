"""Whether the bridge is allowed to boot the MT5 terminal.

The bridge reconnects on every request, and ``mt5.initialize()`` launches
``terminal64.exe`` when no terminal answers. Background polling therefore booted
the terminal continuously: closing the window brought a new one back seconds
later, because the platform polls about once per second whether or not anybody is
looking at it.

The lease below is the only thing that authorises that boot. A connected browser
session renews it; background polling cannot, because polling never renews it.
Nothing here ever terminates the terminal: the platform boots it on demand and
the operator closes it.
"""

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

TTL_ENV = "MT5_TERMINAL_DEMAND_TTL"
DEFAULT_TTL_SECONDS = 120.0

#: Reading the process table costs more than the request it answers; the answer
#: is identical for a couple of seconds at the polling rates the bridge serves.
PROBE_CACHE_SECONDS = 2.0

_probe_lock = threading.Lock()
_probe_cache = (0.0, None)


def demand_ttl() -> float:
    """Lease length in seconds; unusable values fall back to the default."""
    raw = os.getenv(TTL_ENV, "").strip()
    if not raw:
        return DEFAULT_TTL_SECONDS
    try:
        ttl = float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r, using %s", TTL_ENV, raw, DEFAULT_TTL_SECONDS)
        return DEFAULT_TTL_SECONDS
    if ttl <= 0:
        logger.warning("Non-positive %s=%r, using %s", TTL_ENV, raw, DEFAULT_TTL_SECONDS)
        return DEFAULT_TTL_SECONDS
    return ttl


class TerminalDemand:
    """A lease that says a person is using the platform right now."""

    def __init__(self, ttl=demand_ttl, clock=time.monotonic):
        self._ttl = ttl
        self._clock = clock
        self._until = 0.0
        self._lock = threading.Lock()

    def renew(self) -> float:
        """Extend the lease and return how many seconds it now covers."""
        with self._lock:
            self._until = self._clock() + self._ttl()
            return max(0.0, self._until - self._clock())

    def remaining(self) -> float:
        with self._lock:
            return max(0.0, self._until - self._clock())

    def active(self) -> bool:
        return self.remaining() > 0.0

    def revoke(self) -> None:
        with self._lock:
            self._until = 0.0


def terminal_process_running():
    """True/False when the process table answers, ``None`` when it cannot be read.

    ``None`` is not a failure to report, it is an unknown: the caller must keep
    today's behaviour instead of hiding a terminal the operator opened.
    """
    global _probe_cache
    now = time.monotonic()
    with _probe_lock:
        cached_at, cached = _probe_cache
        if now - cached_at < PROBE_CACHE_SECONDS:
            return cached
    try:
        import psutil
    except Exception:
        return None
    try:
        running = False
        for proc in psutil.process_iter(["name"]):
            name = (proc.info.get("name") or "").lower()
            if "terminal64" in name or "metatrader" in name:
                running = True
                break
    except Exception as exc:
        logger.debug("Could not read the process table: %s", exc)
        return None
    with _probe_lock:
        _probe_cache = (now, running)
    return running


def allow_terminal_boot(connector, demand, probe=terminal_process_running) -> bool:
    """Whether ``connector.connect()`` may run, i.e. whether a boot is allowed.

    ``connect()`` is the boot trigger, so withholding it is enough to keep the
    terminal closed. A usable session needs no boot; an active lease authorises
    one; a terminal that already runs is attached to; and an unreadable process
    table fails open so a disarmed probe never strands the operator's terminal.
    """
    from src.live.mt5_bridge_session import session_is_usable

    if session_is_usable(connector):
        return True
    if demand.active():
        return True
    return probe() is not False
