"""Resolve a futures root (``MNQ``) to the contract that is still trading.

Futures symbols carry a month code and a two-digit year (``MNQZ26`` is the
December 2026 E-mini Nasdaq). A workspace saved months ago keeps asking for the
contract that was current then, the broker drops it once it expires, and the
platform answers ``No history found for MNQM26`` for a symbol that is simply not
in the catalogue any more. The root never changes, so the root is what should be
stored and the contract is what should be resolved.
"""
from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Iterable, Optional

__all__ = [
    "contract_expiry",
    "futures_root",
    "pick_active_contract",
    "resolve_active_contract",
]

#: Month codes used by every futures exchange (no I, L, O or P).
MONTH_CODES = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}

_CONTRACT = re.compile(r"^(?P<root>[A-Z]{1,6})(?P<month>[FGHJKMNQUVXZ])(?P<year>\d{2})$")


def futures_root(symbol: str) -> Optional[str]:
    """Return the product code of a dated contract, or ``None``.

    ``MNQZ26`` -> ``MNQ``. A plain root (``MNQ``) or any other symbol yields
    ``None`` so callers can tell "this is a dated contract" from "this is not".
    """
    if not symbol:
        return None
    match = _CONTRACT.match(symbol.strip().upper())
    return match.group("root") if match else None


def _third_friday(year: int, month: int) -> date:
    """Expiry convention for equity-index futures: the third Friday."""
    fridays = [
        week[calendar.FRIDAY]
        for week in calendar.monthcalendar(year, month)
        if week[calendar.FRIDAY]
    ]
    return date(year, month, fridays[2])


def contract_expiry(symbol: str) -> Optional[date]:
    """Last trading day of a dated contract, or ``None`` when it is not one."""
    if not symbol:
        return None
    match = _CONTRACT.match(symbol.strip().upper())
    if not match:
        return None
    month = MONTH_CODES[match.group("month")]
    year = 2000 + int(match.group("year"))
    try:
        return _third_friday(year, month)
    except (ValueError, IndexError):
        return None


def pick_active_contract(
    root: str, symbols: Iterable[str], today: Optional[date] = None
) -> Optional[str]:
    """Return the nearest contract of ``root`` that has not expired yet."""
    if not root:
        return None
    wanted = root.strip().upper()
    reference = today or date.today()
    candidates = []
    for symbol in symbols or ():
        if futures_root(symbol) != wanted:
            continue
        expiry = contract_expiry(symbol)
        if expiry is not None and expiry >= reference:
            candidates.append((expiry, symbol.strip().upper()))
    return min(candidates)[1] if candidates else None


def resolve_active_contract(
    symbol: str, symbols: Iterable[str], today: Optional[date] = None
) -> Optional[str]:
    """Resolve ``symbol`` against ``symbols`` when it is missing or expired.

    Returns the symbol unchanged when the catalogue already carries it, the active
    contract when a dated symbol of the same root is still trading, and ``None``
    when nothing can be resolved (the caller then keeps the original symbol).
    """
    if not symbol:
        return None
    requested = symbol.strip().upper()
    catalogue = {entry.strip().upper() for entry in (symbols or ()) if entry}
    reference = today or date.today()
    expiry = contract_expiry(requested)
    # Being listed is not enough: a broker keeps expired contracts in its catalogue
    # while they have no data to serve, which is exactly the "No history found"
    # case. Only a listed contract that is still trading is kept as asked.
    if requested in catalogue and (expiry is None or expiry >= reference):
        return symbol
    root = futures_root(requested) or requested
    active = pick_active_contract(root, catalogue, today)
    return active
