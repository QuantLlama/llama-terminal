"""Yahoo symbol and history translation, free of heavy dependencies.

The training wizard sends platform symbols (``BTCUSDT``, ``XAUUSD``) and Yahoo
publishes different codes (``BTC-USD``, ``GC=F``); intraday history is also
capped per request. Both rules are pure string work, so they live here instead of
``loader.py``: importing that module pulls scikit-learn, and the CI's minimal lane
installs only the light requirements.
"""

#: Symbols Yahoo publishes under a different code than the trading platform.
#: Checked before the crypto rule, because XAUUSD also ends in USD.
YAHOO_ALIASES = {
    "XAUUSD": "GC=F",   # gold spot -> gold futures
    "XAGUSD": "SI=F",   # silver spot -> silver futures
    "XPTUSD": "PL=F",   # platinum -> platinum futures
    "XPDUSD": "PA=F",   # palladium -> palladium futures
}

#: Stable quotes a platform appends to a crypto base asset.
STABLE_QUOTES = ("USDT", "USDC", "FDUSD", "TUSD", "BUSD", "USD")


def yahoo_symbol(ticker):
    """Translate a platform symbol into the one Yahoo Finance publishes.

    The wizard sends the symbol the chart is showing, so crypto arrives as
    ``BTCUSDT`` / ``BTC/USDT:USDT`` (Yahoo knows it as ``BTC-USD``) and MT5 metal
    spot pairs arrive as ``XAUUSD`` (Yahoo publishes ``GC=F``). Passing those
    through untouched made the download answer "Quote not found for symbol" and
    every training run died before the first epoch.
    """
    if not ticker or not ticker.strip():
        return ticker
    raw = ticker.strip()
    upper = raw.upper()

    # Already a Yahoo symbol: index caret, explicit quote suffix (=F, =X) or a
    # hyphenated pair such as BTC-USD. Returning early also keeps this idempotent.
    if upper.startswith("^") or "=" in upper or "-" in upper:
        return raw

    # Broker decorations: EURUSD.r, BTCUSDT.P. The settle suffix of a perpetual
    # contract is not part of the base pair: BTC/USDT:USDT is BTC/USDT.
    base = upper.split(".", 1)[0].split(":", 1)[0]

    if base in YAHOO_ALIASES:
        return YAHOO_ALIASES[base]

    compact = base.replace("/", "").replace(":", "").replace("_", "")
    for quote in STABLE_QUOTES:
        if compact.endswith(quote) and len(compact) > len(quote):
            return f"{compact[:-len(quote)]}-USD"
    return raw


#: Longest history Yahoo serves per request, by interval. Asking for more makes
#t the whole download fail: "Only 8 days worth of 1m granularity data are allowed".
INTRADAY_LIMITS = {
    "1m": "7d",
    "2m": "59d",
    "5m": "59d",
    "15m": "59d",
    "30m": "59d",
    "60m": "59d",
    "90m": "59d",
    "1h": "59d",
}


def _period_days(period):
    """Rough day count for a Yahoo period string (1d, 2w, 6mo, 1y, max)."""
    text = str(period).strip().lower()
    if text in ("max", "ytd"):
        return 10 ** 6
    if text.endswith("mo"):
        return int(text[:-2] or 1) * 30
    unit = text[-1:]
    value = int(text[:-1] or 1)
    return value * {"d": 1, "w": 7, "m": 30, "y": 365}.get(unit, 1)


def yahoo_period(period, interval):
    """Clamp ``period`` to the history Yahoo actually serves for ``interval``."""
    limit = INTRADAY_LIMITS.get(str(interval).strip().lower())
    if not limit:
        return period
    return limit if _period_days(period) > _period_days(limit) else period
