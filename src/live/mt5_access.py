"""One door to MetaTrader 5: the HTTP bridge in the cloud, the module locally.

``MetaTrader5`` is a Windows-only package. Backend code imported it directly, so
inside the Linux container every one of those paths raised
``ModuleNotFoundError``: ``POST /api/order`` answered 500 and the MT5 tapes
stayed mute, because the bridge sitting in front of the terminal was never
asked. This module is the only place allowed to touch the package; every caller
receives plain dicts with normalised keys, so both runtimes look identical.

Resolution order, everywhere:

1. the bridge, when ``MT5_BRIDGE_URL`` is set (cloud);
2. the local ``MetaTrader5`` module, when it imports (Windows/Wine);
3. ``None``.

Nothing here raises because the package is missing: an unavailable runtime
answers ``None`` (or an empty list) so callers degrade instead of failing.
"""

from __future__ import annotations

import importlib
import logging
import math
import os
import sys

logger = logging.getLogger(__name__)

#: Name of the Windows-only package this module is the single door to.
MT5_MODULE_NAME = "MetaTrader5"

#: Environment variable that points the backend at the Windows bridge.
BRIDGE_URL_ENV = "MT5_BRIDGE_URL"

#: Timeframe values, mirroring the constants the MT5 package exposes so callers
#: never have to import it. The bridge connector already hardcodes the same
#: numbers on ``MT5ApiConnector``.
TIMEFRAMES = {
    "1m": 1,
    "5m": 5,
    "10m": 10,
    "15m": 15,
    "30m": 30,
    "1h": 16385,
    "4h": 16388,
    "1d": 16408,
}
TIMEFRAME_M1 = TIMEFRAMES["1m"]
TIMEFRAME_M5 = TIMEFRAMES["5m"]
TIMEFRAME_M10 = TIMEFRAMES["10m"]
TIMEFRAME_M15 = TIMEFRAMES["15m"]
TIMEFRAME_M30 = TIMEFRAMES["30m"]
TIMEFRAME_H1 = TIMEFRAMES["1h"]
TIMEFRAME_H4 = TIMEFRAMES["4h"]
TIMEFRAME_D1 = TIMEFRAMES["1d"]

COPY_TICKS_ALL = -1
COPY_TICKS_INFO = 1
COPY_TICKS_TRADE = 2


#
# Which runtime answers
#
def bridge_enabled():
    """True when the cloud bridge is configured through ``MT5_BRIDGE_URL``."""
    return bool((os.getenv(BRIDGE_URL_ENV) or "").strip())


def local_module():
    """The local ``MetaTrader5`` module, or ``None`` when it is not installed.

    A runtime without the package is a normal cloud runtime, not an error, so
    the failed import is never re-raised.
    """
    module = sys.modules.get(MT5_MODULE_NAME)
    if module is not None:
        return module
    try:
        return importlib.import_module(MT5_MODULE_NAME)
    except Exception as exc:  # ImportError, but a broken install fails too
        logger.debug("%s is not importable here: %s", MT5_MODULE_NAME, exc)
        return None


def _connector():
    """The bridge client, imported lazily so this module needs no HTTP stack."""
    from src.live.mt5_api_connector import get_mt5_connector

    return get_mt5_connector()


def _bridge_call(connector, name, **kwargs):
    """Call one connector method, answering ``None`` instead of raising.

    Older bridge clients do not expose every method this module prefers, so a
    missing method degrades exactly like a failed request.
    """
    method = getattr(connector, name, None)
    if method is None:
        return None
    try:
        return method(**kwargs)
    except Exception as exc:
        logger.warning("MT5 bridge %s%r failed: %s", name, kwargs, exc)
        return None


#
# Value normalisation
#
def _number(value, default=0.0):
    """Coerce bridge/native values (numpy scalars included) to a finite float."""
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _as_mapping(value):
    """Plain dict for a bridge dict or a native named tuple, else ``None``."""
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)
    to_dict = getattr(value, "_asdict", None)
    if callable(to_dict):
        try:
            return dict(to_dict())
        except Exception:
            return None
    fields = getattr(value, "_fields", None)
    if fields:
        return {name: getattr(value, name, None) for name in fields}
    return None


def _mapping_list(value):
    """List of dicts for a list/tuple payload; a bridge error dict means none."""
    if not isinstance(value, (list, tuple)):
        return []
    rows = []
    for item in value:
        mapping = _as_mapping(item)
        if mapping:
            rows.append(mapping)
    return rows


def _structure_rows(value):
    """List of dicts for a numpy structured array, list or named-tuple payload.

    ``copy_rates_from_pos`` answers a numpy structured array on both runtimes:
    from the package directly and from the bridge client, which rebuilds one out
    of the JSON rows.
    """
    if value is None:
        return []
    names = getattr(getattr(value, "dtype", None), "names", None)
    if names:
        return [{name: value[index][name] for name in names} for index in range(len(value))]
    return _mapping_list(value)


def _same_ticket(left, right):
    if left is None or right is None:
        return False
    return str(left) == str(right)


def _epoch(value):
    """Seconds since the epoch for ints, floats and pandas timestamps."""
    if value is None:
        return 0.0
    if hasattr(value, "timestamp"):
        try:
            return float(value.timestamp())
        except Exception:
            return 0.0
    return _number(value, 0.0)


def _symbol_info_dict(payload):
    """The one shape every ``symbol_info`` answer has, whatever the runtime."""
    point = _number(payload.get("point"))
    digits = int(_number(payload.get("digits")))
    tick_size = _number(payload.get("tick_size"))
    trade_tick_size = _number(payload.get("trade_tick_size"))
    if trade_tick_size <= 0:
        trade_tick_size = tick_size if tick_size > 0 else point
    if tick_size <= 0:
        tick_size = trade_tick_size
    stops_level = payload.get("stops_level")
    if stops_level is None:
        stops_level = payload.get("trade_stops_level")
    return {
        "point": point,
        "digits": digits,
        "tick_size": tick_size,
        "trade_tick_size": trade_tick_size,
        "volume_min": _number(payload.get("volume_min")),
        "volume_max": _number(payload.get("volume_max")),
        "volume_step": _number(payload.get("volume_step")),
        "stops_level": int(_number(stops_level)),
        "trade_contract_size": _number(payload.get("trade_contract_size"), 1.0),
        "visible": bool(payload.get("visible", True)),
    }


def _tick_dict(payload):
    """The one shape every ``symbol_tick`` answer has, whatever the runtime."""
    bid = _number(payload.get("bid"))
    ask = _number(payload.get("ask"))
    last = _number(payload.get("last"))
    if last <= 0 and bid > 0 and ask > 0:
        last = (bid + ask) / 2
    tick_time = _epoch(payload.get("time"))
    time_msc = payload.get("time_msc")
    if time_msc is None:
        time_msc = int(tick_time * 1000)
    return {
        "bid": bid,
        "ask": ask,
        "last": last,
        "time": tick_time,
        "time_msc": int(_number(time_msc)),
        "volume": _number(payload.get("volume")),
    }


def _latest_row(value):
    """Last record of a tick payload (DataFrame, list of dicts or named tuples)."""
    if value is None:
        return None
    records = value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            records = to_dict("records")
        except TypeError:
            records = value
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, (list, tuple)) or not records:
        return None
    return _as_mapping(records[-1])


#
# Symbol metadata
#
def symbol_info(symbol):
    """Normalised symbol metadata, or ``None`` when no runtime can answer.

    Keys: ``point``, ``digits``, ``tick_size``, ``trade_tick_size``,
    ``volume_min``, ``volume_max``, ``volume_step``, ``stops_level``, plus
    ``trade_contract_size`` and ``visible``, which the order and footprint paths
    also need.
    """
    if not symbol:
        return None
    if bridge_enabled():
        return _bridge_symbol_info(symbol)
    module = local_module()
    if module is None:
        return None
    try:
        raw = module.symbol_info(symbol)
    except Exception as exc:
        logger.warning("MetaTrader5 symbol_info(%s) failed: %s", symbol, exc)
        return None
    payload = _as_mapping(raw)
    if payload is None:
        return None
    return _symbol_info_dict(payload)


def _bridge_symbol_info(symbol):
    connector = _connector()
    payload = _as_mapping(_bridge_call(connector, "symbol_info", symbol=symbol)) or {}
    if "point" not in payload or "digits" not in payload:
        # Fall back to the details route, which answers point/digits/tick_size
        # but carries no volume limits.
        details = _as_mapping(_bridge_call(connector, "get_symbol_details", symbol=symbol))
        for key, value in (details or {}).items():
            payload.setdefault(key, value)
    if not payload:
        return None
    return _symbol_info_dict(payload)


def order_size_rules(symbol):
    """``volume_min``/``volume_max``/``volume_step`` for a symbol, or ``None``.

    ``contract_size`` rides along because the symbol endpoint also reports it and
    reading it twice would cost a second bridge round trip.
    """
    info = symbol_info(symbol)
    if not info:
        return None
    return {
        "volume_min": info["volume_min"],
        "volume_max": info["volume_max"],
        "volume_step": info["volume_step"],
        "contract_size": info["trade_contract_size"],
    }


#
# Market data
#
def symbol_tick(symbol):
    """Latest tick as ``bid``/``ask``/``last``/``time``/``volume`` (+``time_msc``).

    The bridge has no single-tick route, so the newest row of its tick history is
    used; when that is empty the last traded price still answers as a flat tick.
    """
    if not symbol:
        return None
    if bridge_enabled():
        return _bridge_symbol_tick(symbol)
    module = local_module()
    if module is None:
        return None
    try:
        raw = module.symbol_info_tick(symbol)
    except Exception as exc:
        logger.warning("MetaTrader5 symbol_info_tick(%s) failed: %s", symbol, exc)
        return None
    payload = _as_mapping(raw)
    if payload is None:
        return None
    return _tick_dict(payload)


def _bridge_symbol_tick(symbol):
    connector = _connector()
    row = _latest_row(_bridge_call(connector, "get_recent_ticks", symbol=symbol, n=1))
    if row is not None:
        return _tick_dict(row)
    price = _number(_bridge_call(connector, "get_current_price", symbol=symbol))
    if price <= 0:
        return None
    return {
        "bid": price,
        "ask": price,
        "last": price,
        "time": 0.0,
        "time_msc": 0,
        "volume": 0.0,
    }


def rates_from_pos(symbol, timeframe="1m", count=100):
    """Candles from the newest position as plain dicts, or ``None``.

    ``None`` means no runtime could answer at all; an empty list means the
    runtime answered with no history. ``time`` stays in seconds, exactly what
    ``copy_rates_from_pos`` reports, so existing timestamp conversions keep
    working.
    """
    if not symbol:
        return None
    timeframe = timeframe_value(timeframe)
    if bridge_enabled():
        raw = _bridge_call(
            _connector(),
            "copy_rates_from_pos",
            symbol=symbol,
            timeframe=timeframe,
            start_pos=0,
            count=count,
        )
        return None if raw is None else _structure_rows(raw)
    module = local_module()
    if module is None:
        return None
    method = getattr(module, "copy_rates_from_pos", None)
    if method is None:
        return None
    # MT5 needs initialize() before it will answer, and the package is idempotent,
    # so calling it when a terminal is already up costs nothing. Without it a
    # local install that nothing else initialised returns None instead of candles.
    initialize = getattr(module, "initialize", None)
    if initialize is not None:
        try:
            initialize()
        except Exception as exc:
            logger.warning("MetaTrader5 initialize() failed: %s", exc)
            return None
    try:
        raw = method(symbol, timeframe, 0, count)
    except Exception as exc:
        logger.warning("MetaTrader5 copy_rates_from_pos(%s) failed: %s", symbol, exc)
        return None
    return None if raw is None else _structure_rows(raw)


#
# Positions and orders
#
def positions(ticket=None, symbol=None):
    """Open positions as dicts, optionally filtered by ``ticket`` or ``symbol``."""
    if bridge_enabled():
        connector = _connector()
        payload = _bridge_call(connector, "get_positions", symbol=symbol, ticket=ticket)
        return _mapping_list(payload)
    return _module_records("positions_get", ticket=ticket, symbol=symbol)


def orders(ticket=None, symbol=None):
    """Pending orders as dicts, optionally filtered by ``ticket`` or ``symbol``."""
    if bridge_enabled():
        connector = _connector()
        rows = _mapping_list(_bridge_call(connector, "get_pending_orders", symbol=symbol))
        if ticket is None:
            return rows
        return [row for row in rows if _same_ticket(row.get("ticket"), ticket)]
    return _module_records("orders_get", ticket=ticket, symbol=symbol)


def _module_records(method_name, ticket=None, symbol=None):
    module = local_module()
    if module is None:
        return []
    method = getattr(module, method_name, None)
    if method is None:
        return []
    kwargs = {}
    if ticket is not None:
        try:
            kwargs["ticket"] = int(ticket)
        except (TypeError, ValueError):
            kwargs["ticket"] = ticket
    elif symbol:
        kwargs["symbol"] = symbol
    try:
        raw = method(**kwargs)
    except Exception as exc:
        logger.warning("MetaTrader5 %s%r failed: %s", method_name, kwargs, exc)
        return []
    return _mapping_list(raw)


#
# Terminal
#
def mt5_version():
    """Terminal version as text, or ``None`` when nothing can report one.

    The bridge exposes no version route, so a cloud runtime answers ``None``;
    that is a missing fact, not a failure.
    """
    if bridge_enabled():
        return None
    module = local_module()
    if module is None:
        return None
    version = getattr(module, "version", None)
    if not callable(version):
        return None
    try:
        value = version()
    except Exception as exc:
        logger.warning("MetaTrader5 version() failed: %s", exc)
        return None
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return " ".join(str(part) for part in value)
    return str(value)


def timeframe_value(timeframe, default=TIMEFRAME_M1):
    """MT5 numeric timeframe for ``"5m"``/``"1h"``/... without importing MT5."""
    if isinstance(timeframe, (int, float)):
        return int(timeframe)
    return TIMEFRAMES.get(str(timeframe or "").lower(), default)
