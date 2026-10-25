"""Public (unauthenticated) crypto market data for the tape and the DOM.

The feed endpoints - ``/api/v2/feed/trades/*``, ``/api/v2/feed/dom/*``,
``/api/v2/feed/book/*`` and ``/api/v2/ws/feed`` - are unauthenticated and read
only from :class:`~src.services.market_data_engine.engine.MarketDataEngine`.
Until now the engine's crypto poll could only build an *account* connector, which
needs an active trading tenant (``src/services/active_tenant.py``); after every
container restart nobody has selected one, so the tape and the DOM stayed empty
while charts kept working (charts build a connector from the request token).

This module is the missing piece: a read-only connector over public endpoints.
It never holds API keys, never reads an account and can never place an order. It
resolves perpetual symbols and fetches the ticker, the recent trades and the
order-book snapshot, with the same return contracts as
``src/live/crypto_connector.py`` so every consumer of the feed keeps working.

``ccxt`` is imported inside the constructor on purpose: the module must stay
importable (and testable) without the exchange library.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from src.services.crypto_proxy import apply_proxy

logger = logging.getLogger(__name__)

#: Exchange id used when the caller and the environment are both silent.
DEFAULT_EXCHANGE_ID = "binanceusdm"

#: Environment variable that selects the public exchange.
EXCHANGE_ENV = "CRYPTO_PUBLIC_EXCHANGE"

#: This platform serves perpetual futures only: never spot, margin or options.
EXCLUDED_MARKET_TYPES = ("spot", "margin", "option", "index")

#: Quotes a perpetual contract can settle against, most common first.
PRIORITY_QUOTES = ("USDT", "USDC", "USD")

#: Depth limits exchanges accept verbatim; anything else is rounded up.
VALID_BOOK_LIMITS = (5, 10, 20, 50, 100, 500, 1000)

#: A failed ``load_markets`` is retried at most this often (seconds).
_CONNECT_RETRY_SECONDS = 5.0


class PublicMarketDataConnector:
    """Read-only market data for one exchange, with no credentials at all.

    The interface mirrors the market-data half of
    :class:`src.live.crypto_connector.CryptoConnector` so the feed cannot tell
    the two apart: ``connected``, ``connect()``, ``close()``, ``_resolve_sym``,
    ``get_tick``, ``get_trades`` and ``get_book_snapshot`` return the same shapes.
    """

    def __init__(self, exchange_id: str):
        import ccxt  # imported here so tests can stub sys.modules["ccxt"]

        self.exchange_id = str(exchange_id or DEFAULT_EXCHANGE_ID).strip().lower()
        if not self.exchange_id:
            raise ValueError("a public connector needs an exchange id")

        self._connected = False
        self._lock = threading.RLock()
        self._last_connect_attempt = 0.0
        self._perp_markets: Dict[str, Dict[str, Any]] = {}

        # Public data only: no apiKey, no secret, no password, no account.
        self.exchange = getattr(ccxt, self.exchange_id)(
            {
                "enableRateLimit": True,
                "options": {
                    "adjustForTimeDifference": True,
                    "defaultType": "swap",
                },
            }
        )
        apply_proxy(self.exchange)
        logger.info(
            "[CRYPTO-PUBLIC] %s initialized for public market data only",
            self.exchange_id,
        )

    # ── lifecycle ──────────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        """Load the perpetual market list; safe to call from every poll."""
        if self._connected:
            return True
        with self._lock:
            if self._connected:
                return True
            now = time.time()
            if now - self._last_connect_attempt < _CONNECT_RETRY_SECONDS:
                return False
            self._last_connect_attempt = now
            try:
                markets = self.exchange.load_markets() or {}
            except Exception as exc:
                logger.error(
                    "[CRYPTO-PUBLIC] %s could not load markets: %s",
                    self.exchange_id,
                    exc,
                )
                self._connected = False
                return False
            if not markets:
                markets = getattr(self.exchange, "markets", None) or {}
            self._perp_markets = {
                symbol: market
                for symbol, market in markets.items()
                if self._is_perpetual_market(market)
            }
            self._connected = bool(self._perp_markets)
            if self._connected:
                logger.info(
                    "[CRYPTO-PUBLIC] %s connected: %s perpetual markets",
                    self.exchange_id,
                    len(self._perp_markets),
                )
            else:
                logger.warning(
                    "[CRYPTO-PUBLIC] %s exposes no perpetual markets",
                    self.exchange_id,
                )
            return self._connected

    def close(self) -> None:
        """Forget the connection state; a later poll reconnects."""
        with self._lock:
            self._connected = False
            self._perp_markets = {}

    # ── symbol resolution ──────────────────────────────────────────────────

    def _is_perpetual_market(self, market: Dict[str, Any]) -> bool:
        """True only for perpetual/swap contracts, never for spot."""
        if not market:
            return False
        market_type = str(market.get("type") or "").lower()
        if market_type in EXCLUDED_MARKET_TYPES:
            return False
        if market.get("optionType") is not None:
            return False
        settle = market.get("settle") or ""
        return market_type in ("swap", "future") and (
            bool(market.get("linear")) or settle in ("USDT", "USDC", "USD", "BTC", "XBT", "ETH")
        )

    def _resolve_sym(self, symbol: str) -> Optional[str]:
        """Resolve ``symbol`` to a perpetual market, or ``None``.

        Same variant ladder as ``CryptoConnector._resolve_sym``:
        ``BASE/QUOTE:QUOTE`` first, then ``BASE-QUOTE:QUOTE``, then
        ``BASE/QUOTE`` and finally ``BASEQUOTE``. A spot-only symbol never wins.
        """
        if not symbol:
            return None

        all_markets = getattr(self.exchange, "markets", None) or {}
        markets_to_search = self._perp_markets or all_markets
        if not markets_to_search:
            logger.warning(
                "[CRYPTO-PUBLIC] %s has no perpetual markets loaded for %s",
                self.exchange_id,
                symbol,
            )
            return None

        if symbol in markets_to_search and self._is_perpetual_market(
            markets_to_search[symbol]
        ):
            return symbol

        clean_sym = (
            symbol.replace("/", "").replace(":", "").replace("_", "").replace("-", "").upper()
        )

        for quote in PRIORITY_QUOTES:
            if not clean_sym.endswith(quote):
                continue
            base = clean_sym[: -len(quote)]
            variants = (
                f"{base}/{quote}:{quote}",
                f"{base}-{quote}:{quote}",
                f"{base}/{quote}",
                f"{base}{quote}",
            )
            for variant in variants:
                for candidate in (variant, variant.upper()):
                    market = markets_to_search.get(candidate)
                    if market and self._is_perpetual_market(market):
                        return candidate
            # An already loaded but unfiltered market list may still hold it.
            for variant in variants:
                for candidate in (variant, variant.upper()):
                    market = all_markets.get(candidate)
                    if market and self._is_perpetual_market(market):
                        return candidate

        # Greedy fallback for exchanges with non-standard naming (e.g. XBTUSD).
        base_asset = clean_sym.replace("USDT", "").replace("USDC", "").replace("USD", "")
        if base_asset:
            for market_sym, market in markets_to_search.items():
                market_upper = market_sym.upper()
                if base_asset in market_upper and self._is_perpetual_market(market):
                    if "USD" in market_upper or "XBT" in market_upper:
                        return market_sym
        return None

    # ── public market data ─────────────────────────────────────────────────

    def get_tick(self, symbol: str) -> Dict[str, Any]:
        """Ticker with the same keys ``CryptoConnector.get_tick`` returns."""
        now = time.time()
        self.connect()
        fetched_symbol = self._resolve_sym(symbol)
        try:
            ticker = self.exchange.fetch_ticker(fetched_symbol) or {}
        except Exception as exc:
            logger.error(
                "[CRYPTO-PUBLIC] %s ticker failed for %s: %s",
                self.exchange_id,
                symbol,
                exc,
            )
            return {
                "symbol": symbol,
                "fetched_symbol": fetched_symbol,
                "exchange": self.exchange_id,
                "bid": 0.0,
                "ask": 0.0,
                "last": 0.0,
                "baseVolume": 0.0,
                "quoteVolume": 0.0,
                "timestamp": 0,
                "time": now,
            }

        timestamp = ticker.get("timestamp")
        return {
            "symbol": symbol,
            "fetched_symbol": fetched_symbol,
            "exchange": self.exchange_id,
            "bid": float(ticker.get("bid") or 0.0),
            "ask": float(ticker.get("ask") or 0.0),
            "last": float(ticker.get("last") or 0.0),
            "baseVolume": float(ticker.get("baseVolume") or 0.0),
            "quoteVolume": float(ticker.get("quoteVolume") or 0.0),
            "timestamp": timestamp or 0,
            "time": (timestamp / 1000.0) if timestamp else now,
        }

    def get_trades(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Recent public trades: seconds, price, amount, UPPER side and an id."""
        self.connect()
        fetched_symbol = self._resolve_sym(symbol)
        try:
            raw_trades = self.exchange.fetch_trades(fetched_symbol, limit=limit) or []
        except Exception as exc:
            logger.error(
                "[CRYPTO-PUBLIC] %s trades failed for %s: %s",
                self.exchange_id,
                symbol,
                exc,
            )
            return []

        trades: List[Dict[str, Any]] = []
        for trade in raw_trades:
            timestamp = trade.get("timestamp")
            trade_id = trade.get("id") or (
                f"{timestamp or 0}_{trade.get('price', 0)}_{trade.get('amount', 0)}"
            )
            trades.append(
                {
                    "timestamp": (float(timestamp) / 1000.0) if timestamp else time.time(),
                    "price": float(trade.get("price") or 0.0),
                    "amount": float(trade.get("amount") or 0.0),
                    "side": str(trade.get("side") or "buy").upper(),
                    "id": trade_id,
                }
            )
        return trades

    def get_book_snapshot(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        """Order-book snapshot with the ``CryptoConnector`` shape."""
        self.connect()
        fetched_symbol = self._resolve_sym(symbol)
        book_limit = next(
            (value for value in VALID_BOOK_LIMITS if limit <= value),
            VALID_BOOK_LIMITS[-1],
        )
        try:
            book = self.exchange.fetch_order_book(fetched_symbol, limit=book_limit) or {}
        except Exception as exc:
            logger.error(
                "[CRYPTO-PUBLIC] %s order book failed for %s: %s",
                self.exchange_id,
                symbol,
                exc,
            )
            return {"bids": [], "asks": [], "timestamp": 0.0}

        raw_timestamp = book.get("timestamp")
        return {
            "bids": [
                {"price": level[0], "size": level[1]}
                for level in (book.get("bids") or [])
            ],
            "asks": [
                {"price": level[0], "size": level[1]}
                for level in (book.get("asks") or [])
            ],
            "timestamp": (raw_timestamp / 1000.0) if raw_timestamp else time.time(),
        }

    def get_ohlcv(
        self, symbol: str, timeframe: str = "1m", limit: int = 100
    ) -> List[List]:
        """Recent candles; the engine polls them to keep the live bar moving."""
        self.connect()
        fetched_symbol = self._resolve_sym(symbol)
        try:
            return list(
                self.exchange.fetch_ohlcv(fetched_symbol, timeframe, limit=limit) or []
            )
        except Exception as exc:
            logger.error(
                "[CRYPTO-PUBLIC] %s candles failed for %s: %s",
                self.exchange_id,
                symbol,
                exc,
            )
            return []

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<PublicMarketDataConnector {self.exchange_id} connected={self._connected}>"


# ── process-wide cache, one connector per exchange id ───────────────────

_connectors: Dict[str, PublicMarketDataConnector] = {}
_connectors_lock = threading.RLock()


def _exchange_id(exchange_id: Optional[str] = None) -> str:
    candidate = exchange_id or os.getenv(EXCHANGE_ENV) or DEFAULT_EXCHANGE_ID
    resolved = str(candidate).strip().lower()
    return resolved or DEFAULT_EXCHANGE_ID


def get_public_data_connector(
    exchange_id: Optional[str] = None,
) -> PublicMarketDataConnector:
    """Return the cached public connector for ``exchange_id``.

    The exchange id defaults to ``CRYPTO_PUBLIC_EXCHANGE`` and then to
    ``binanceusdm``. The first request for an exchange connects it, so callers do
    not have to.
    """
    exchange = _exchange_id(exchange_id)
    with _connectors_lock:
        connector = _connectors.get(exchange)
        created = connector is None
        if created:
            connector = PublicMarketDataConnector(exchange)
            _connectors[exchange] = connector
    if created:
        connector.connect()
    return connector


def reset_public_data_connector(exchange_id: Optional[str] = None) -> None:
    """Drop the cached connector(s) and close them.

    Without an ``exchange_id`` every cached exchange is dropped, which is what a
    test or a deployment reconfigure wants.
    """
    with _connectors_lock:
        if exchange_id is None:
            dropped = list(_connectors.values())
            _connectors.clear()
        else:
            single = _connectors.pop(_exchange_id(exchange_id), None)
            dropped = [single] if single else []
    for connector in dropped:
        try:
            connector.close()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("[CRYPTO-PUBLIC] close failed: %s", exc)
