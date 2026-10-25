"""Training must translate platform symbols into Yahoo ones before downloading.

The wizard sends the symbol the chart is showing: ``BTCUSDT`` for crypto and the
broker symbol for MT5 (``XAUUSD``). Yahoo knows neither. ``load_data`` passed the
ticker through untouched, so the download answered

    HTTP Error 404: Quote not found for symbol: BTCUSDT
    ValueError: No data found for ticker BTCUSDT

and every crypto training run died before the first epoch. These cases pin the
translation, which is pure and needs no network.
"""
import pytest

from src.data.loader import yahoo_symbol


@pytest.mark.parametrize(
    "ticker, expected",
    [
        ("BTCUSDT", "BTC-USD"),
        ("BTCUSDT.P", "BTC-USD"),
        ("BTC/USDT", "BTC-USD"),
        ("BTC/USDT:USDT", "BTC-USD"),
        ("ethusdt", "ETH-USD"),
        ("SOLUSDC", "SOL-USD"),
        ("XAUUSD", "GC=F"),
        ("XAGUSD", "SI=F"),
    ],
)
def test_translates_platform_symbols_to_yahoo(ticker, expected):
    assert yahoo_symbol(ticker) == expected


@pytest.mark.parametrize(
    "ticker",
    ["AAPL", "MSFT", "^VIX", "ES=F", "BTC-USD", "eurusd=x"],
)
def test_leaves_symbols_yahoo_already_understands_alone(ticker):
    assert yahoo_symbol(ticker) == ticker


def test_is_idempotent():
    once = yahoo_symbol("BTCUSDT")
    assert yahoo_symbol(once) == once
