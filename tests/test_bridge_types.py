"""Contract tests for the MT5 bridge normalization layer.

The web API must serve both MT5 connectors:

* native (Windows/Wine) returns MetaTrader5 named tuples read with attributes
  such as ``pos.ticket``;
* the HTTP bridge connector returns plain dicts.

``src/live/bridge_types.py`` provides the small normalization layer that lets a
single API code path read both, plus the position payload mapping used by
``GET /api/positions``.
"""

from collections import namedtuple

import pytest

from src.live.bridge_types import AttrDict, normalize, positions_to_web

NativePosition = namedtuple(
    "NativePosition",
    ["ticket", "symbol", "type", "volume", "price_open", "price_current", "sl", "tp", "profit", "swap", "comment"],
)


def test_dict_keys_are_readable_as_attributes():
    payload = normalize({"ticket": 42, "symbol": "EURUSD"})

    assert isinstance(payload, AttrDict)
    assert payload.ticket == 42
    assert payload.symbol == "EURUSD"
    assert payload["ticket"] == 42


def test_missing_attribute_raises_attribute_error():
    payload = normalize({"ticket": 42})

    with pytest.raises(AttributeError):
        payload.profit


def test_hasattr_is_false_for_missing_keys():
    payload = normalize({"ticket": 42})

    assert hasattr(payload, "ticket") is True
    assert hasattr(payload, "price_current") is False


def test_normalize_converts_nested_dicts_and_dict_lists():
    payload = normalize(
        {
            "account": {"balance": 1000.0, "currency": "USD"},
            "positions": [{"ticket": 1, "profit": 2.5}, {"ticket": 2, "profit": -1.0}],
        }
    )

    assert isinstance(payload["account"], AttrDict)
    assert payload.account.balance == 1000.0
    assert payload.account.currency == "USD"
    assert [pos.ticket for pos in payload.positions] == [1, 2]
    assert isinstance(payload.positions[0], AttrDict)
    assert payload.positions[0].profit == 2.5


def test_normalize_returns_none_unchanged():
    assert normalize(None) is None


def test_normalize_returns_string_unchanged():
    # A bridge error payload iterated as if it were a position list is exactly
    # what produced "'str' object has no attribute 'ticket'" in production.
    assert normalize("detail") == "detail"
    assert isinstance(normalize("detail"), str)


def test_normalize_leaves_native_named_tuple_untouched():
    native = NativePosition(7, "EURUSD", 0, 0.1, 1.1, 1.2, 1.0, 1.3, 5.0, -0.1, "native")

    assert normalize(native) is native
    assert normalize([native])[0] is native


def test_positions_to_web_maps_bridge_position_payload():
    bridge_positions = normalize(
        [
            {
                "ticket": 11,
                "symbol": "EURUSD",
                "type": 1,
                "volume": 0.5,
                "price_open": 1.10000,
                "price_current": 1.10500,
                "sl": 1.09500,
                "tp": 1.11000,
                "profit": 12.5,
                "swap": -0.25,
                "comment": "bridge",
            }
        ]
    )

    assert positions_to_web(bridge_positions) == [
        {
            "ticket": 11,
            "symbol": "EURUSD",
            "type": "SELL",
            "volume": 0.5,
            "entry_price": 1.10000,
            "current_price": 1.10500,
            "sl": 1.09500,
            "tp": 1.11000,
            "profit": 12.5,
            "swap": -0.25,
            "comment": "bridge",
        }
    ]


def test_positions_to_web_keeps_native_positions_working():
    native = [NativePosition(5, "GBPUSD", 0, 0.2, 1.25, 1.26, 1.24, 1.27, 3.0, 0.0, "native")]

    assert positions_to_web(native) == [
        {
            "ticket": 5,
            "symbol": "GBPUSD",
            "type": "BUY",
            "volume": 0.2,
            "entry_price": 1.25,
            "current_price": 1.26,
            "sl": 1.24,
            "tp": 1.27,
            "profit": 3.0,
            "swap": 0.0,
            "comment": "native",
        }
    ]


def test_positions_to_web_defaults_missing_bridge_fields():
    [mapped] = positions_to_web(normalize([{"ticket": 3, "symbol": "USDJPY", "type": 0}]))

    assert mapped == {
        "ticket": 3,
        "symbol": "USDJPY",
        "type": "BUY",
        "volume": 0,
        "entry_price": 0,
        "current_price": 0,
        "sl": 0,
        "tp": 0,
        "profit": 0,
        "swap": 0,
        "comment": "",
    }


def test_as_list_discards_error_payloads():
    from src.live.bridge_types import as_list

    assert as_list([{"a": 1}]) == [{"a": 1}]
    assert as_list({"detail": "invalid bridge token"}) == []
    assert as_list("boom") == []
    assert as_list(None) == []


def test_as_list_accepts_tuples_from_native_connector():
    from src.live.bridge_types import as_list

    assert as_list(({"a": 1},)) == [{"a": 1}]
