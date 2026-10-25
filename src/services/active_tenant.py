"""The active trading tenant for background work.

One engine process serves many authenticated users, but the loops and engine
internals that keep a trading session alive - the crypto account monitor, the
market-data engine, the order gateway and the NinjaTrader replicator - run
outside any request and therefore cannot read a bearer token. They read this
holder instead.

It is written only by an authenticated action: selecting a master account or
connecting an account (see ``src/platform/api/accounts_api.py``). When it is
empty those consumers must skip their work and log once; they must never fall
back to ``default_user`` or to "the first row in the table", because either
fallback would trade another user's account.

This is deliberately not a cache of "everybody's accounts": there is exactly one
active trading user per process, and clearing it stops the background work.
"""
from __future__ import annotations

import logging
from typing import Optional, Set

__all__ = [
    "clear_active_user_id",
    "get_active_user_id",
    "note_missing_active_user",
    "set_active_user_id",
]

_active_user_id: Optional[str] = None
_missing_tenant_logged: Set[str] = set()

SKIP_MESSAGE = (
    "no active trading user is set; sign in and select a master account before "
    "this service can trade"
)


def set_active_user_id(user_id: str) -> str:
    """Record the tenant an authenticated action selected.

    The value must be a non-empty id; anything else raises ``TypeError`` so a
    caller cannot accidentally activate a shared or synthetic tenant.
    """
    global _active_user_id
    if not isinstance(user_id, str) or not user_id.strip():
        raise TypeError(
            "set_active_user_id requires a non-empty user id; there is no shared "
            "trading tenant"
        )
    _active_user_id = user_id
    return _active_user_id


def get_active_user_id() -> Optional[str]:
    """Return the active trading tenant, or ``None`` when nobody selected one."""
    return _active_user_id


def clear_active_user_id(user_id: Optional[str] = None) -> None:
    """Clear the active tenant, or clear it only if ``user_id`` owns it.

    Passing the id that is signing out keeps a concurrent user's session from
    being switched off by somebody else's logout.
    """
    global _active_user_id
    if user_id is not None and _active_user_id != user_id:
        return
    _active_user_id = None
    _missing_tenant_logged.clear()


def note_missing_active_user(consumer: str, logger: logging.Logger) -> None:
    """Log once per consumer that its work was skipped for lack of a tenant.

    A four-times-a-second loop must not flood the log with the same line, but an
    operator still has to be able to see why a service is idle.
    """
    if consumer in _missing_tenant_logged:
        return
    _missing_tenant_logged.add(consumer)
    logger.warning("[active-tenant] %s skipped: %s", consumer, SKIP_MESSAGE)
