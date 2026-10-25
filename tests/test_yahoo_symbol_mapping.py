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


# ── per-request history limits ──────────────────────────────────────────────

from src.data.loader import yahoo_period


@pytest.mark.parametrize(
    "period, interval, expected",
    [
        ("1y", "1m", "7d"),      # Yahoo serves 8 days of 1m at most
        ("59d", "1m", "7d"),
        ("5d", "1m", "5d"),      # asking for less than the cap is fine
        ("1y", "5m", "59d"),     # 2m-1h are capped at 60 days
        ("1y", "1h", "59d"),
        ("1y", "1d", "1y"),      # daily history has no intraday cap
        ("max", "1h", "59d"),
        ("6mo", "1h", "59d"),    # 180 days requested, 60 served
        ("1mo", "1h", "1mo"),    # 30 days fits under the cap
    ],
)
def test_caps_intraday_periods_to_what_yahoo_serves(period, interval, expected):
    assert yahoo_period(period, interval) == expected
