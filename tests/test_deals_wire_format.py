"""The deals payload must reach the browser as objects, not as positional arrays.

A namedtuple serialises to JSON as an array, so the client read d.time and got
undefined and every filter dropped the row. The backend never saw the bug because
it reads the same rows through getattr.
"""
import json
from collections import namedtuple

from src.platform.api.deals_cache import deals_as_dicts

TradeDeal = namedtuple("TradeDeal", ["ticket", "type", "entry", "time", "symbol", "profit"])


def test_namedtuples_become_objects_over_the_wire():
    rows = [TradeDeal(1, 1, 1, 1792939877, "MESZ26", 12.5)]

    payload = json.loads(json.dumps({"deals": deals_as_dicts(rows)}))

    assert payload["deals"] == [
        {"ticket": 1, "type": 1, "entry": 1, "time": 1792939877, "symbol": "MESZ26", "profit": 12.5}
    ]
    assert payload["deals"][0]["time"] == 1792939877


def test_dicts_pass_through_untouched():
    rows = [{"ticket": 2, "time": 1792897200}]
    assert deals_as_dicts(rows) == [{"ticket": 2, "time": 1792897200}]


def test_empty_and_none_are_safe():
    assert deals_as_dicts([]) == []
    assert deals_as_dicts(None) == []


def test_order_and_length_are_preserved():
    rows = [TradeDeal(i, 0, 0, 1792939877 + i, "X", 0.0) for i in range(19)]
    result = deals_as_dicts(rows)
    assert len(result) == 19
    assert [r["ticket"] for r in result] == list(range(19))
