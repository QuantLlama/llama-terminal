"""Lazy MT5 session handling for the HTTP bridge.

The bridge keeps a single MT5 connection for the whole platform. The terminal
can drop it (restart, logout, broker disconnect), so every request re-ensures
the session instead of failing until a client happens to call /api/connect.
"""

import logging

logger = logging.getLogger(__name__)


def ensure_connected(connector) -> bool:
    """Return True when the connector has a live MT5 session."""
    if connector is None:
        return False
    if getattr(connector, "connected", False):
        return True
    try:
        connected = bool(connector.connect())
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("MT5 reconnect failed: %s", exc)
        return False
    if not connected:
        logger.warning("MT5 session still unavailable after reconnect attempt")
    return connected
