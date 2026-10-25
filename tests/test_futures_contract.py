"""A saved futures workspace must survive a contract rollover.

The operator keeps ``MNQ`` (or an old ``MNQM26``) in a workspace for months. The
broker only lists live contracts, so asking for an expired one answers
``No history found``. These cases pin the resolution against a fixed catalogue and
a fixed date, with no network and no broker.
"""
from datetime import date

import pytest

from src.utils.futures_contract import (
    contract_expiry,
    futures_root,
    pick_active_contract,
    resolve_active_contract,
)

OCT_2026 = date(2026, 10, 25)

#: What a broker lists in late October 2026: the December contract is current,
#: the June one already expired, and the March 2027 one is listed already.
CATALOGUE = ["MNQM26", "MNQZ26", "MNQH27", "MNQH20", "NQM26", "NQZ26"]


@pytest.mark.parametrize(
    "symbol, expected",
    [("MNQZ26", "MNQ"), ("mnqz26", "MNQ"), ("MNQ", None), ("BTCUSDT", None), ("", None)],
)
def test_futures_root_reads_the_product_code(symbol, expected):
    assert futures_root(symbol) == expected


def test_contract_expiry_is_the_third_friday():
    # December 2026: Fridays are 4, 11, 18 and 25.
    assert contract_expiry("MNQZ26") == date(2026, 12, 18)
    assert contract_expiry("MNQ") is None


def test_picks_the_nearest_contract_that_has_not_expired():
    assert pick_active_contract("MNQ", CATALOGUE, OCT_2026) == "MNQZ26"


def test_ignores_expired_contracts_even_if_they_are_nearest():
    # MNQM26 is nearer in time but expired in June 2026.
    assert pick_active_contract("MNQ", CATALOGUE, OCT_2026) != "MNQM26"


def test_returns_none_when_no_contract_of_that_root_is_listed():
    assert pick_active_contract("CL", CATALOGUE, OCT_2026) is None


def test_a_plain_root_resolves_to_the_active_contract():
    assert resolve_active_contract("MNQ", CATALOGUE, OCT_2026) == "MNQZ26"


def test_an_expired_contract_resolves_to_the_active_one():
    assert resolve_active_contract("MNQM26", CATALOGUE, OCT_2026) == "MNQZ26"


def test_a_listed_contract_is_kept_as_asked():
    assert resolve_active_contract("MNQH27", CATALOGUE, OCT_2026) == "MNQH27"


def test_a_symbol_without_any_contract_in_the_catalogue_is_left_alone():
    """Non-futures symbols and unknown products must not be rewritten."""
    assert resolve_active_contract("AAPL", CATALOGUE, OCT_2026) is None


def test_the_rollover_moves_the_resolution_forward():
    """By March 2027 the December contract expired: the answer must change."""
    assert resolve_active_contract("MNQ", CATALOGUE, date(2027, 3, 1)) == "MNQH27"


def test_connector_resolves_through_the_broker_catalogue(monkeypatch):
    """The connector caches the catalogue and delegates the choice to the resolver."""
    from src.live.mt5_api_connector import MT5ApiConnector

    calls = {"n": 0}

    def fake_symbols_get(group=None, pattern=None):
        calls["n"] += 1
        # MNQZ99 is far enough away that this assertion never depends on today.
        return [{"name": name} for name in ("MNQM26", "MNQZ99")]

    connector = object.__new__(MT5ApiConnector)
    connector.symbols_get = fake_symbols_get

    assert connector.resolve_contract("MNQ") == "MNQZ99", "a plain root finds the live contract"
    assert connector.resolve_contract("MNQM26") == "MNQZ99", "an expired contract rolls forward"
    assert calls["n"] == 1, "the catalogue is cached between requests"

    connector.resolve_contract("MNQ", force=True)
    assert calls["n"] == 2, "force refreshes the catalogue"


def test_connector_leaves_unknown_symbols_alone(monkeypatch):
    from src.live.mt5_api_connector import MT5ApiConnector

    connector = object.__new__(MT5ApiConnector)
    connector.symbols_get = lambda group=None, pattern=None: [{"name": "MNQZ99"}]

    assert connector.resolve_contract("AAPL") == "AAPL"
