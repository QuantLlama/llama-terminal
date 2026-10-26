"""Lazy MT5 session handling for the HTTP bridge.

The bridge keeps a single MT5 connection for the whole platform. The terminal
can drop it (restart, logout, broker disconnect), so every request re-ensures
the session instead of failing until a client happens to call /api/connect.
"""

import logging

logger = logging.getLogger(__name__)


def session_is_usable(connector) -> bool:
    """Trust ``connected`` only when the connector can prove it is still live.

    The native connector exposes ``is_alive()`` because its flag outlives the
    terminal session. Connectors without a probe (the HTTP client, whose remote
    session is re-ensured by the bridge) keep the previous contract.
    """
    if not getattr(connector, "connected", False):
        return False
    probe = getattr(connector, "is_alive", None)
    if probe is None:
        return True
    try:
        return bool(probe())
    except Exception:
        return False


def ensure_connected(connector) -> bool:
    """Return True when the connector has a live MT5 session."""
    if connector is None:
        return False
    if session_is_usable(connector):
        return True
    try:
        connected = bool(connector.connect())
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("MT5 reconnect failed: %s", exc)
        return False
    if not connected:
        logger.warning("MT5 session still unavailable after reconnect attempt")
    return connected
