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
    """A lease that says a person is using the platform right now.

    Renewal and revocation travel over HTTP from another process, so they can
    arrive out of order: a renewal still in flight when the last session closes
    would otherwise re-arm the lease after its release, and a slow release would
    revoke the lease of a session opened a moment later. Callers pass a monotonic
    ``seq``; a delivery older than the last applied one is ignored, which makes
    the outcome independent of arrival order.
    """

    def __init__(self, ttl=demand_ttl, clock=time.monotonic):
        self._ttl = ttl
        self._clock = clock
        self._until = 0.0
        self._applied_seq = None
        self._lock = threading.Lock()

    def _is_stale(self, seq) -> bool:
        """True when this delivery lost the race to an already applied one."""
        return (
            seq is not None
            and self._applied_seq is not None
            and seq < self._applied_seq
        )

    def _mark(self, seq):
        if seq is not None:
            self._applied_seq = seq

    def renew(self, seq=None):
        """Extend the lease and return its seconds, or ``None`` when stale."""
        with self._lock:
            if self._is_stale(seq):
                logger.info("Ignoring a stale terminal demand renewal (seq %s)", seq)
                return None
            self._mark(seq)
            self._until = self._clock() + self._ttl()
            return max(0.0, self._until - self._clock())

    def remaining(self) -> float:
        with self._lock:
            return max(0.0, self._until - self._clock())

    def active(self) -> bool:
        return self.remaining() > 0.0

    def revoke(self, seq=None) -> bool:
        """Drop the lease; returns False when the delivery was stale."""
        with self._lock:
            if self._is_stale(seq):
                logger.info("Ignoring a stale terminal demand release (seq %s)", seq)
                return False
            self._mark(seq)
            self._until = 0.0
            return True


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
    one; a terminal that already runs is attached to.

    An unreadable process table withholds the boot on purpose. Failing open here
    would recreate the exact loop this module exists to stop: on a runtime where
    ``psutil`` is missing, every background poll would boot the terminal again.
    ``psutil`` is a declared deploy dependency, so an unknown answer is a
    transient probe failure and the next request retries.
    """
    from src.live.mt5_bridge_session import session_is_usable

    if session_is_usable(connector):
        return True
    if demand.active():
        return True
    answer = probe()
    if answer is True:
        return True
    if answer is None:
        logger.warning(
            "Could not read the process table; withholding the MT5 terminal boot"
        )
    return False
