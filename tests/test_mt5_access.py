"""``mt5_access``: one door to MetaTrader 5 for both runtimes.

``MetaTrader5`` is a Windows-only package. Inside the Linux container the only
way to reach the terminal is the HTTP bridge, so every helper here must answer
from the bridge when ``MT5_BRIDGE_URL`` is set, from the local package when it
imports, and ``None`` (never an exception) when neither is available.

No HTTP is involved: the bridge connector is replaced by a stand-in, and the
local package by a ``sys.modules`` stub, so each documented normalised key is
asserted against known values instead of the operator's live terminal.
"""
import sys
from collections import namedtuple
from types import SimpleNamespace

import numpy as np
import pytest

from src.live import mt5_access

#: Keys every ``symbol_info`` answer must carry, whatever answered it.
SYMBOL_INFO_KEYS = (
    "point",
    "digits",
    "tick_size",
    "trade_tick_size",
    "volume_min",
    "volume_max",
    "volume_step",
    "stops_level",
)

#: Keys every ``symbol_tick`` answer must carry.
TICK_KEYS = ("bid", "ask", "last", "time", "volume")

BRIDGE_URL = "https://bridge.example.internal:8443"


def _record(name, **values):
    """Build the named tuple shape the native MetaTrader5 package returns."""
    Record = namedtuple(name, values.keys())
    return Record(**values)


class FakeBridge:
    """Stand-in for ``MT5ApiConnector``: records calls, answers canned payloads."""

    def __init__(self, **payloads):
        self.payloads = payloads
        self.calls = []

    def _answer(self, name, symbol, **kwargs):
        self.calls.append((name, symbol, kwargs))
        return self.payloads.get(name)

    def symbol_info(self, symbol):
        return self._answer("symbol_info", symbol)

    def get_symbol_details(self, symbol):
        return self._answer("get_symbol_details", symbol)

    def get_recent_ticks(self, symbol, n=1000):
        return self._answer("get_recent_ticks", symbol, n=n)

    def get_current_price(self, symbol):
        return self._answer("get_current_price", symbol)

    def get_positions(self, symbol=None, ticket=None):
        return self._answer("get_positions", symbol, ticket=ticket)

    def get_pending_orders(self, symbol=None):
        return self._answer("get_pending_orders", symbol)

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        self.calls.append(
            (
                "copy_rates_from_pos",
                symbol,
                {"timeframe": timeframe, "start_pos": start_pos, "count": count},
            )
        )
        return self.payloads.get("copy_rates_from_pos")


@pytest.fixture
def bridge(monkeypatch):
    """A configured bridge with a mocked connector and no local package."""
    monkeypatch.setenv(mt5_access.BRIDGE_URL_ENV, BRIDGE_URL)
    # ``None`` in sys.modules makes the import fail, exactly like the container.
    monkeypatch.setitem(sys.modules, mt5_access.MT5_MODULE_NAME, None)
    connector = FakeBridge()
    monkeypatch.setattr(mt5_access, "_connector", lambda: connector)
    return connector


@pytest.fixture
def local(monkeypatch):
    """No bridge configured, with the Windows package present as a stub."""
    monkeypatch.delenv(mt5_access.BRIDGE_URL_ENV, raising=False)
    calls = []
    info = _record(
        "SymbolInfo",
        point=0.25,
        digits=2,
        tick_size=0.25,
        trade_tick_size=0.25,
        volume_min=1.0,
        volume_max=50.0,
        volume_step=1.0,
        trade_stops_level=12,
        trade_contract_size=2.0,
        visible=True,
    )
    tick = _record(
        "Tick",
        bid=18000.0,
        ask=18000.25,
        last=0.0,
        time=1700000000,
        volume=7,
        time_msc=1700000000000,
    )
    position = _record("Position", ticket=11, symbol="MNQ", volume=1.0)
    order = _record("Order", ticket=22, symbol="MNQ")
    candles = np.array(
        [(1700000000, 18000.0), (1700003600, 18010.0)],
        dtype=[("time", "i8"), ("close", "f8")],
    )

    def answer(name, value):
        def call(*args, **kwargs):
            calls.append((name, args, kwargs))
            return value

        return call

    module = SimpleNamespace(
        symbol_info=answer("symbol_info", info),
        symbol_info_tick=answer("symbol_info_tick", tick),
        positions_get=answer("positions_get", (position,)),
        orders_get=answer("orders_get", (order,)),
        copy_rates_from_pos=answer("copy_rates_from_pos", candles),
        version=lambda: (4040, "15 Jan 2024", "MT5 5.0"),
    )
    monkeypatch.setitem(sys.modules, mt5_access.MT5_MODULE_NAME, module)
    return SimpleNamespace(module=module, calls=calls, info=info, tick=tick)


#
# Runtime resolution
#
def test_bridge_enabled_only_when_the_bridge_url_is_set(monkeypatch):
    monkeypatch.delenv(mt5_access.BRIDGE_URL_ENV, raising=False)
    assert mt5_access.bridge_enabled() is False

    monkeypatch.setenv(mt5_access.BRIDGE_URL_ENV, BRIDGE_URL)
    assert mt5_access.bridge_enabled() is True


def test_local_module_is_none_when_the_package_is_missing(monkeypatch):
    monkeypatch.delenv(mt5_access.BRIDGE_URL_ENV, raising=False)
    monkeypatch.setitem(sys.modules, mt5_access.MT5_MODULE_NAME, None)

    assert mt5_access.local_module() is None


def test_local_module_answers_the_installed_package(local):
    assert mt5_access.local_module() is local.module


#
# symbol_info
#
def test_bridge_answers_symbol_info_with_the_documented_keys(bridge):
    bridge.payloads["symbol_info"] = {
        "point": 0.25,
        "digits": 2,
        "trade_tick_size": 0.25,
        "trade_stops_level": 12,
        "volume_min": 1.0,
        "volume_max": 50.0,
        "volume_step": 1.0,
        "trade_contract_size": 2.0,
        "visible": True,
    }

    info = mt5_access.symbol_info("MNQ")

    assert set(SYMBOL_INFO_KEYS) <= set(info)
    assert info["point"] == 0.25
    assert info["digits"] == 2
    assert info["tick_size"] == 0.25
    assert info["trade_tick_size"] == 0.25
    assert info["volume_min"] == 1.0
    assert info["volume_max"] == 50.0
    assert info["volume_step"] == 1.0
    assert info["stops_level"] == 12
    assert [call[0] for call in bridge.calls] == ["symbol_info"]


def test_bridge_is_preferred_even_when_the_local_package_exists(bridge, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("the local package must not be asked when MT5_BRIDGE_URL is set")

    monkeypatch.setitem(
        sys.modules,
        mt5_access.MT5_MODULE_NAME,
        SimpleNamespace(symbol_info=forbidden, symbol_info_tick=forbidden),
    )
    bridge.payloads["symbol_info"] = {"point": 0.25, "digits": 2}

    info = mt5_access.symbol_info("MNQ")

    assert info["point"] == 0.25
    assert info["digits"] == 2


def test_bridge_falls_back_to_the_details_route_without_volume_limits(bridge):
    bridge.payloads["get_symbol_details"] = {
        "point": 0.01,
        "digits": 3,
        "tick_size": 0.01,
        "stops_level": 0,
        "broker_type": "cfd",
    }

    info = mt5_access.symbol_info("EURUSD")

    assert info["point"] == 0.01
    assert info["digits"] == 3
    assert info["tick_size"] == 0.01
    # Unknown limits stay zero rather than being invented.
    assert info["volume_min"] == 0.0
    assert info["volume_max"] == 0.0
    assert info["volume_step"] == 0.0
    assert [call[0] for call in bridge.calls] == ["symbol_info", "get_symbol_details"]


def test_bridge_answers_none_for_an_unknown_symbol(bridge):
    assert mt5_access.symbol_info("NOPE") is None


def test_local_module_answers_symbol_info_when_no_bridge_is_configured(local):
    info = mt5_access.symbol_info("MNQ")

    assert set(SYMBOL_INFO_KEYS) <= set(info)
    assert info["point"] == 0.25
    assert info["tick_size"] == 0.25
    assert info["volume_min"] == 1.0
    assert info["volume_max"] == 50.0
    assert info["volume_step"] == 1.0
    assert info["stops_level"] == 12
    assert local.calls == [("symbol_info", ("MNQ",), {})]


#
# Degradation: no bridge, no package, no exception
#
def test_every_helper_degrades_without_bridge_and_without_package(monkeypatch):
    monkeypatch.delenv(mt5_access.BRIDGE_URL_ENV, raising=False)
    monkeypatch.setitem(sys.modules, mt5_access.MT5_MODULE_NAME, None)

    assert mt5_access.symbol_info("MNQ") is None
    assert mt5_access.symbol_tick("MNQ") is None
    assert mt5_access.order_size_rules("MNQ") is None
    assert mt5_access.mt5_version() is None
    assert mt5_access.positions() == []
    assert mt5_access.positions(ticket=11) == []
    assert mt5_access.orders(ticket=22) == []
    assert mt5_access.rates_from_pos("MNQ", "1m", 10) is None


def test_a_failing_bridge_call_degrades_instead_of_raising(bridge):
    def explode(**kwargs):
        raise RuntimeError("bridge is down")

    bridge.get_positions = explode
    bridge.symbol_info = explode

    assert mt5_access.positions() == []
    assert mt5_access.symbol_info("MNQ") is None


#
# symbol_tick
#
def test_bridge_answers_the_newest_tick(bridge):
    bridge.payloads["get_recent_ticks"] = [
        {
            "time": 1700000000,
            "bid": 18000.0,
            "ask": 18000.25,
            "last": 18000.25,
            "volume": 7,
            "time_msc": 1700000000000,
        }
    ]

    tick = mt5_access.symbol_tick("MNQ")

    assert set(TICK_KEYS) <= set(tick)
    assert tick["bid"] == 18000.0
    assert tick["ask"] == 18000.25
    assert tick["last"] == 18000.25
    assert tick["time"] == 1700000000.0
    assert tick["volume"] == 7.0
    assert bridge.calls == [("get_recent_ticks", "MNQ", {"n": 1})]


def test_bridge_tick_reads_the_newest_row_of_a_dataframe(bridge):
    import pandas as pd

    bridge.payloads["get_recent_ticks"] = pd.DataFrame(
        [
            {"time": 1699999999, "bid": 1.0, "ask": 1.5, "last": 1.25, "volume": 1},
            {"time": 1700000000, "bid": 18000.0, "ask": 18000.5, "last": 18000.5, "volume": 9},
        ]
    )

    tick = mt5_access.symbol_tick("MNQ")

    assert tick["bid"] == 18000.0
    assert tick["last"] == 18000.5
    assert tick["volume"] == 9.0


def test_bridge_tick_midpoints_when_the_broker_reports_no_last_price(bridge):
    bridge.payloads["get_recent_ticks"] = [
        {"time": 5, "bid": 100.0, "ask": 101.0, "last": 0.0, "volume": 0}
    ]

    assert mt5_access.symbol_tick("EURUSD")["last"] == 100.5


def test_bridge_tick_falls_back_to_the_current_price_route(bridge):
    bridge.payloads["get_current_price"] = 18000.5

    tick = mt5_access.symbol_tick("MNQ")

    assert tick["bid"] == 18000.5
    assert tick["ask"] == 18000.5
    assert tick["last"] == 18000.5


def test_local_module_answers_the_tick_when_no_bridge_is_configured(local):
    tick = mt5_access.symbol_tick("MNQ")

    assert set(TICK_KEYS) <= set(tick)
    assert tick["bid"] == 18000.0
    assert tick["ask"] == 18000.25
    assert tick["last"] == 18000.125
    assert tick["volume"] == 7.0
    assert local.calls == [("symbol_info_tick", ("MNQ",), {})]


#
# positions / orders
#
def test_bridge_answers_positions_and_orders_as_dicts(bridge):
    bridge.payloads["get_positions"] = [{"ticket": 11, "symbol": "MNQ", "volume": 1.0}]
    bridge.payloads["get_pending_orders"] = [
        {"ticket": 22, "symbol": "MNQ"},
        {"ticket": 33, "symbol": "NQ"},
    ]

    assert mt5_access.positions(ticket=11) == [
        {"ticket": 11, "symbol": "MNQ", "volume": 1.0}
    ]
    assert ("get_positions", None, {"ticket": 11}) in bridge.calls
    assert mt5_access.orders(ticket=33) == [{"ticket": 33, "symbol": "NQ"}]


def test_bridge_error_payload_is_not_mistaken_for_positions(bridge):
    bridge.payloads["get_positions"] = {"detail": "Not connected"}

    assert mt5_access.positions() == []


def test_local_module_answers_positions_by_ticket(local):
    assert mt5_access.positions(ticket="11") == [
        {"ticket": 11, "symbol": "MNQ", "volume": 1.0}
    ]
    assert local.calls == [("positions_get", (), {"ticket": 11})]


#
# order_size_rules
#
def test_order_size_rules_expose_the_volume_limits(bridge):
    bridge.payloads["symbol_info"] = {
        "point": 0.25,
        "digits": 2,
        "volume_min": 0.1,
        "volume_max": 20.0,
        "volume_step": 0.1,
        "trade_contract_size": 2.0,
    }

    rules = mt5_access.order_size_rules("MNQ")

    assert rules["volume_min"] == 0.1
    assert rules["volume_max"] == 20.0
    assert rules["volume_step"] == 0.1
    assert rules["contract_size"] == 2.0


#
# mt5_version
#
def test_mt5_version_reports_the_local_terminal(local):
    assert mt5_access.mt5_version() == "4040 15 Jan 2024 MT5 5.0"


def test_mt5_version_is_none_through_the_bridge(bridge):
    # The bridge exposes no version route: a missing fact, not a failure.
    assert mt5_access.mt5_version() is None


#
# rates_from_pos
#
def test_bridge_answers_candles_as_plain_dicts(bridge):
    bridge.payloads["copy_rates_from_pos"] = np.array(
        [(1700000000.0, 18000.0, 18010.0, 17990.0, 18005.0, 12.0)],
        dtype=[
            ("time", "f8"),
            ("open", "f8"),
            ("high", "f8"),
            ("low", "f8"),
            ("close", "f8"),
            ("tick_volume", "f8"),
        ],
    )

    rows = mt5_access.rates_from_pos("MNQ", "5m", 60)

    assert len(rows) == 1
    assert rows[0]["time"] == 1700000000.0
    assert rows[0]["open"] == 18000.0
    assert rows[0]["close"] == 18005.0
    assert rows[0]["tick_volume"] == 12.0
    # "5m" reaches the bridge as the MT5 numeric value, never as a string.
    assert bridge.calls == [
        ("copy_rates_from_pos", "MNQ", {"timeframe": 5, "start_pos": 0, "count": 60})
    ]


def test_bridge_candles_accept_plain_records(bridge):
    bridge.payloads["copy_rates_from_pos"] = [
        {"time": 1700000000, "open": 1.0, "close": 2.0}
    ]

    assert mt5_access.rates_from_pos("MNQ", "1m", 10) == [
        {"time": 1700000000, "open": 1.0, "close": 2.0}
    ]


def test_bridge_candles_answer_none_when_the_request_fails(bridge):
    assert mt5_access.rates_from_pos("MNQ", "1m", 10) is None


def test_local_module_answers_candles(local):
    rows = mt5_access.rates_from_pos("MNQ", "15m", 30)

    assert [row["time"] for row in rows] == [1700000000, 1700003600]
    assert rows[0]["close"] == 18000.0
    assert local.calls == [("copy_rates_from_pos", ("MNQ", 15, 0, 30), {})]


def test_an_unknown_timeframe_still_asks_for_one_minute(bridge):
    bridge.payloads["copy_rates_from_pos"] = []

    assert mt5_access.rates_from_pos("MNQ", "bogus", 10) == []
    assert bridge.calls[0][2]["timeframe"] == mt5_access.TIMEFRAME_M1


#
# Constants callers no longer import from the package
#
@pytest.mark.parametrize(
    "name,value",
    [
        ("1m", 1),
        ("5m", 5),
        ("10m", 10),
        ("15m", 15),
        ("30m", 30),
        ("1h", 16385),
        ("4h", 16388),
        ("1d", 16408),
    ],
)
def test_timeframe_values_match_the_mt5_constants(name, value):
    assert mt5_access.timeframe_value(name) == value


def test_timeframe_value_defaults_to_one_minute():
    assert mt5_access.timeframe_value("nope") == mt5_access.TIMEFRAME_M1
    assert mt5_access.timeframe_value(None) == mt5_access.TIMEFRAME_M1


def test_tick_copy_flags_match_the_mt5_constants():
    assert mt5_access.COPY_TICKS_ALL == -1
    assert mt5_access.COPY_TICKS_INFO == 1
    assert mt5_access.COPY_TICKS_TRADE == 2
