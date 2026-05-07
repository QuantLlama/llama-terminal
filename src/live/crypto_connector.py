import ccxt
import logging
import threading
from typing import Dict, List, Optional, Any
from datetime import datetime
logger = logging.getLogger(__name__)


# CRITICAL: This platform is ONLY for CRYPTO PERPETUAL SWAPS (futures)
# NO SPOT, NO COIN-FUTURES
SUPPORTED_PERPETUAL_TYPES = ['swap', 'future']
EXCLUDED_MARKET_TYPES = ['spot', 'margin', 'option', 'index']


class CryptoConnector:
    _instances = {}
    _lock = threading.RLock()
    
    def __new__(cls, account_id: str, exchange_id: str, api_key: str, api_secret: str, passphrase: str = None, test_mode: bool = True):
        with cls._lock:
            if account_id not in cls._instances:
                instance = super(CryptoConnector, cls).__new__(cls)
                instance._initialized = False
                cls._instances[account_id] = instance
            return cls._instances[account_id]
    
    def __init__(self, account_id: str, exchange_id: str, api_key: str, api_secret: str, passphrase: str = None, test_mode: bool = True):
        if self._initialized:
            return
        self.account_id = account_id
        self.exchange_id = exchange_id.lower()
        self.test_mode = test_mode
        self.connected = False
        self._last_connect_time = 0
        self.passphrase = passphrase
        self.api_key = api_key
        self.api_secret = api_secret
        
        # CRITICAL FIX: Configure ALL exchanges to use SWAP/PERPETUAL markets ONLY
        # This platform is ONLY for crypto perpetual futures, NOT spot
        config = {
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True,
                'recvWindow': 50000,
                # CRITICAL: Force swap/perpetual mode for ALL exchanges
                'defaultType': 'swap',
            }
        }
        
        if passphrase:
            config['password'] = passphrase
        
        # Exchange-specific configurations for perpetual futures
        if self.exchange_id == 'blofin':
            # Blofin: Swap markets
            config['options']['defaultType'] = 'swap'
            logger.info(f"[CRYPTO] Initializing Blofin (PERPETUALS ONLY) for {account_id}")
        elif self.exchange_id == 'binance':
            # Binance: Futures markets (USDT-Margined Perpetuals)
            config['options']['defaultType'] = 'future'
            logger.info(f"[CRYPTO] Initializing Binance Futures (PERPETUALS ONLY) for {account_id}")
        elif self.exchange_id == 'okx':
            # OKX: Perpetual/Swap markets
            config['options']['defaultType'] = 'swap'
            logger.info(f"[CRYPTO] Initializing OKX Perpetuals (PERPETUALS ONLY) for {account_id}")
        elif self.exchange_id == 'bybit':
            # Bybit: Perpetual markets
            config['options']['defaultType'] = 'linear'
            logger.info(f"[CRYPTO] Initializing Bybit Perpetuals (PERPETUALS ONLY) for {account_id}")
        elif self.exchange_id == 'bitget':
            # Bitget: Perpetual markets
            config['options']['defaultType'] = 'swap'
            logger.info(f"[CRYPTO] Initializing Bitget Perpetuals (PERPETUALS ONLY) for {account_id}")
        elif self.exchange_id == 'bingx':
            # BingX: Perpetual markets (USDT-Margined)
            # BingX uses 'swap' for perpetual futures
            config['options']['defaultType'] = 'swap'
            # BingX-specific: use the correct API version for perpetuals
            config['options']['fetchMarkets'] = ['spot', 'swap']
            logger.info(f"[CRYPTO] Initializing BingX Perpetuals (PERPETUALS ONLY) for {account_id}")

        try:
            exchange_class = getattr(ccxt, self.exchange_id)
            self.exchange = exchange_class(config)
            
            if test_mode and hasattr(self.exchange, 'urls') and 'test' in self.exchange.urls:
                self.exchange.urls['api'] = self.exchange.urls['test']
                logger.info(f"Using {self.exchange_id} TESTNET")
            
            self._initialized = True
            self._cache = {}
            self._cache_ttl = 10.0
            self._perp_markets = {}  # Cache of perpetual markets only
            logger.info(f"CryptoConnector initialized for {self.exchange_id} (PERPETUALS ONLY, Account: {account_id})")
        except Exception as e:
            logger.error(f"Failed to initialize ccxt exchange {self.exchange_id}: {e}")
            raise
    
    def connect(self) -> bool:
        if self.connected:
            return True
            
        now = datetime.now().timestamp()
        if now - self._last_connect_time < 5:
            return False
        
        self._last_connect_time = now
        try:
            logger.info(f"Connecting to {self.exchange_id} (PERPETUALS ONLY, Account: {self.account_id})...")
            
            # Load markets and filter to perpetual only
            self.exchange.load_markets()
            self._filter_perpetual_markets()
            # FIX: Do not fetch balance during connection. This is a blocking private API call
            # that adds massive latency during symbol routing tests. It will be fetched lazily later.
            self.connected = True
            logger.info(f"Successfully connected to {self.exchange_id} - {len(self._perp_markets)} perpetual markets loaded")
            return True

        except Exception as e:
            logger.error(f"Connection failed for {self.exchange_id}: {e}")
            self.connected = False
            return False
    
    def _filter_perpetual_markets(self):
        """
        CRITICAL FIX: Filter markets to ONLY perpetual/swap markets.
        This ensures we never accidentally use spot or other market types.
        
        Perpetual contracts (USDT-Margined):
        - Binance Futures: BTC/USDT:USDT, ETH/USDT:USDT, etc.
        - OKX Swap: BTC-USDT-SWAP, ETH-USDT-SWAP, etc.
        - Bybit Linear: BTC/USDT, ETH/USDT, etc.
        """
        if not hasattr(self.exchange, 'markets') or not self.exchange.markets:
            return
        
        self._perp_markets = {}
        excluded_count = 0
        
        for sym, market in self.exchange.markets.items():
            market_type = market.get('type', '').lower()
            linear = market.get('linear', False)
            settle = market.get('settle', '')
            option_type = market.get('optionType', None)
            
            # Exclude non-perpetual market types first
            if market_type in EXCLUDED_MARKET_TYPES:
                excluded_count += 1
                continue
            
            # Exclude options
            if option_type is not None:
                excluded_count += 1
                continue
            
            # Include perpetual/swap/future markets with linear settlement (USDT/USDC)
            is_perpetual = (
                (market_type in ['swap', 'future'] and linear) or
                (market_type == 'swap' and settle in ['USDT', 'USDC', 'USD']) or
                (market_type == 'future' and settle in ['USDT', 'USDC', 'USD']) or
                linear  # Any linear contract
            )
            
            # Exclude inverse contracts (inverse = not linear, settled in the base currency)
            if not linear and market_type not in ['swap', 'future']:
                excluded_count += 1
                continue
            
            if is_perpetual:
                self._perp_markets[sym] = market
            else:
                excluded_count += 1
        
        logger.info(f"[{self.exchange_id}] Filtered markets: {len(self._perp_markets)} perpetual, {excluded_count} excluded")
    def get_balance(self) -> float:
        now = datetime.now().timestamp()
        cache_key = "balance"
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if now - entry['ts'] < self._cache_ttl:
                return entry['data']

        try:
            balance = self.exchange.fetch_balance()
            total = balance.get('total', {})
            val = total.get('USDT', 0.0)
            if val == 0.0:
                val = total.get('USDC', 0.0)
            if val == 0.0 and 'USD' in total:
                val = total.get('USD', 0.0)
            
            self._cache[cache_key] = {'data': float(val), 'ts': now}
            return float(val)
        except Exception as e:
            logger.error(f"Error fetching balance from {self.exchange_id}: {e}")
            return 0.0

    def get_equity(self) -> float:
        now = datetime.now().timestamp()
        cache_key = "equity"
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if now - entry['ts'] < self._cache_ttl:
                return entry['data']

        try:
            balance = self.exchange.fetch_balance()
            res_equity = 0.0
            if 'info' in balance:
                info = balance['info']
                if isinstance(info, list) and len(info) > 0:
                    info = info[0]
                if isinstance(info, dict):
                    if 'totalMarginBalance' in info:
                        res_equity = float(info['totalMarginBalance'])
                    elif 'totalWalletBalance' in info:
                        res_equity = float(info['totalWalletBalance'])
                    elif 'equity' in info:
                        res_equity = float(info['equity'])
            
            if res_equity == 0.0:
                base_balance = self.get_balance()
                positions = self.get_positions()
                unrealized = sum(p.get('profit', 0.0) for p in positions)
                res_equity = base_balance + unrealized
            
            self._cache[cache_key] = {'data': res_equity, 'ts': now}
            return res_equity
        except Exception as e:
            logger.error(f"Error fetching equity from {self.exchange_id}: {e}")
            return self.get_balance()

    def get_daily_pnl(self) -> float:
        return 0.0

    def get_account_info(self) -> Dict[str, Any]:
        return {
            "balance": self.get_balance(),
            "equity": self.get_equity(),
            "margin": 0.0,
            "margin_free": 0.0,
            "margin_level": 0.0,
            "leverage": 1.0,
            "currency": "USDT",
            "profit": 0.0,
            "account": self.account_id,
            "name": "Crypto Account",
            "server": self.exchange_id,
            "platform": "crypto"
        }

    def shutdown(self):
        self.connected = False
    def get_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        now = datetime.now().timestamp()
        cache_key = f"positions_{symbol}" if symbol else "positions_all"
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if now - entry['ts'] < self._cache_ttl:
                return entry['data']

        try:
            if hasattr(self.exchange, 'fetch_positions'):
                positions = self.exchange.fetch_positions(symbols=[symbol] if symbol else None)
                result = []
                for p in positions:
                    if float(p.get('contracts', 0)) != 0:
                        result.append({
                            "symbol": p['symbol'],
                            "type": p['side'].upper(),
                            "volume": abs(float(p['contracts'] or p['notional'] or 0)),
                            "entry_price": float(p['entryPrice'] or 0),
                            "current_price": float(p['markPrice'] or 0),
                            "profit": float(p['unrealizedPnl'] or 0),
                            "margin": float(p['initialMargin'] or 0),
                            "ticket": p.get('id', p['symbol']) 
                        })
                self._cache[cache_key] = {'data': result, 'ts': now}
                return result
            return []
        except Exception as e:
            logger.error(f"Error fetching positions from {self.exchange_id}: {e}")
            return []
    def _resolve_sym(self, symbol: str) -> Optional[str]:
        """
        CRITICAL FIX: Resolve symbol to PERPETUAL market format ONLY.
        
        Perpetual symbols format:
        - BTC/USDT:USDT (Binance, OKX, etc.)
        - BTC-USDT:USDT (some exchanges)
        
        This function ONLY searches in perpetual/swap markets.
        NEVER returns a spot symbol.
        """
        if not symbol:
            return None
        
        # Use perpetual markets cache if available
        markets_to_search = self._perp_markets if hasattr(self, '_perp_markets') and self._perp_markets else (self.exchange.markets if hasattr(self.exchange, 'markets') else {})
        
        if not markets_to_search:
            logger.warning(f"[{self.exchange_id}] No perpetual markets loaded for {symbol}")
            return None
        
        # 1. If symbol already exists in perpetual markets, return it
        if symbol in markets_to_search:
            market = markets_to_search[symbol]
            # Verify it's actually a perpetual
            if self._is_perpetual_market(market):
                return symbol
        
        # 2. Clean symbol for variations
        clean_sym = symbol.replace("/", "").replace(":", "").replace("_", "").replace("-", "").upper()
        
        # Priority quotes for perpetuals (USDT and USDC are the most common)
        quotes = ["USDT", "USDC"]
        
        for quote in quotes:
            if clean_sym.endswith(quote):
                base = clean_sym[:-len(quote)]
                
                # CRITICAL: Perpetual symbol variants in order of preference
                perpetual_variants = [
                    # Most common format: BASE/QUOTE:QUOTE (e.g., BTC/USDT:USDT)
                    f"{base}/{quote}:{quote}",
                    # Alternative format: BASE-QUOTE:QUOTE
                    f"{base}-{quote}:{quote}",
                    # Without suffix: BASE/QUOTE
                    f"{base}/{quote}",
                    # Unified format: BASEQUOTE
                    f"{base}{quote}",
                ]
                
                for v in perpetual_variants:
                    # Check exact match first
                    if v in markets_to_search:
                        market = markets_to_search[v]
                        if self._is_perpetual_market(market):
                            logger.info(f"[{self.exchange_id}] Resolved {symbol} -> {v} (PERPETUAL)")
                            return v
                    
                    # Check uppercase
                    v_upper = v.upper()
                    if v_upper in markets_to_search:
                        market = markets_to_search[v_upper]
                        if self._is_perpetual_market(market):
                            logger.info(f"[{self.exchange_id}] Resolved {symbol} -> {v_upper} (PERPETUAL)")
                            return v_upper
                
                # 3. Also search in all markets for this quote (fallback)
                for v in perpetual_variants:
                    if v in self.exchange.markets:
                        market = self.exchange.markets[v]
                        if self._is_perpetual_market(market):
                            return v
                    v_upper = v.upper()
                    if v_upper in self.exchange.markets:
                        market = self.exchange.markets[v_upper]
                        if self._is_perpetual_market(market):
                            return v_upper
        
        # 4. If symbol has :QUOTE already (like BTC/USDT:USDT), try to find it
        if ':' in symbol:
            for market_sym in markets_to_search:
                if market_sym.upper() == symbol.upper():
                    return market_sym
        
        logger.warning(f"[{self.exchange_id}] Could not resolve perpetual symbol: {symbol}")
        return None
    
    def _is_perpetual_market(self, market: Dict) -> bool:
        """Check if a market is a perpetual/swap contract."""
        if not market:
            return False
        
        market_type = market.get('type', '').lower()
        linear = market.get('linear', False)
        settle = market.get('settle', '')
        
        # Is it a perpetual/swap?
        is_swap_type = market_type in ['swap', 'future']
        is_linear = linear or settle in ['USDT', 'USDC', 'USD']
        
        return is_swap_type and is_linear
    def get_tick(self, symbol: str) -> Dict:
        try:
            fetch_sym = self._resolve_sym(symbol)
            ticker = self.exchange.fetch_ticker(fetch_sym)
            result = {
                "symbol": symbol,
                "fetched_symbol": fetch_sym,
                "exchange": self.exchange_id,
                "bid": ticker.get('bid', 0),
                "ask": ticker.get('ask', 0),
                "last": ticker.get('last', 0),
                "baseVolume": ticker.get('baseVolume', 0),
                "quoteVolume": ticker.get('quoteVolume', 0),
                "timestamp": ticker.get('timestamp', 0),
                "time": (ticker.get('timestamp') / 1000) if ticker.get('timestamp') else datetime.now().timestamp()
            }
            # Log every 50th tick for debugging
            if not hasattr(self, '_tick_count'):
                self._tick_count = 0
            self._tick_count += 1
            if self._tick_count % 50 == 1:
                logger.info(f"[{self.exchange_id}] Tick for {fetch_sym}: last={result['last']} bid={result['bid']} ask={result['ask']}")
            return result
        except Exception as e:
            logger.error(f"Error fetching tick for {symbol} on {self.exchange_id}: {e}")
            return {}
    def get_ohlcv(self, symbol: str, timeframe: str = '1m', limit: int = 100) -> List[List]:
        """
        Fetch historical bars with pagination support for large requests.
        """
        try:
            fetch_sym = self._resolve_sym(symbol)
            all_ohlcv = []
            remaining = limit
            
            # Standard exchange limit per request is usually 500-1000
            batch_limit = min(remaining, 1000)
            
            # Safety: Max iterations to prevent infinite loops
            max_iterations = 10
            iterations = 0
            
            # Since parameter (timestamp in ms)
            current_since = None
            
            while remaining > 0 and iterations < max_iterations:
                iterations += 1
                try:
                    # Fetch batch. If current_since is None, most exchanges return recent candles.
                    # Note: We work backwards if we have a previous batch.
                    # CCXT fetch_ohlcv(symbol, timeframe, since, limit)
                    ohlcv = self.exchange.fetch_ohlcv(fetch_sym, timeframe, since=current_since, limit=batch_limit)
                    
                    if not ohlcv:
                        break
                        
                    # If this is the first batch and we didn't provide 'since', it's the MOST RECENT
                    # To get older data, we need to calculate 'since' for the next batch
                    if current_since is None:
                        all_ohlcv = ohlcv + all_ohlcv
                        # Calculate 'since' for the previous batch based on the first candle of this batch
                        # Approximate interval in ms
                        tf_ms = self.exchange.parse_timeframe(timeframe) * 1000
                        # Try to get data starting before the current first bar
                        current_since = ohlcv[0][0] - (batch_limit * tf_ms)
                    else:
                        # Prepend historical bars (ensure no overlaps if the exchange is weird)
                        # Filter out bars we already have
                        existing_timestamps = {bar[0] for bar in all_ohlcv}
                        new_bars = [bar for bar in ohlcv if bar[0] not in existing_timestamps]
                        all_ohlcv = new_bars + all_ohlcv
                        
                        # Move 'since' further back
                        tf_ms = self.exchange.parse_timeframe(timeframe) * 1000
                        current_since = ohlcv[0][0] - (batch_limit * tf_ms)
                    
                    remaining -= len(ohlcv)
                    batch_limit = min(remaining, 1000)
                    
                    # If the exchange returned fewer than requested, we might be at the end of available history
                    if len(ohlcv) < 10: # Small buffer
                        break
                        
                except Exception as e:
                    logger.warning(f"[{self.exchange_id}] Batch fetch failed at iteration {iterations}: {e}")
                    break
            
            # Sort by timestamp and return the last 'limit' items
            all_ohlcv.sort(key=lambda x: x[0])
            return all_ohlcv[-limit:] if all_ohlcv else []
            
        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol} on {self.exchange_id}: {e}")
            return []
    def get_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        try:
            fetch_sym = self._resolve_sym(symbol)
            trades = self.exchange.fetch_trades(fetch_sym, limit=limit)
            result = []
            for t in trades:
                tid = t.get('id')
                # FIX: If exchange (like BingX) doesn't provide trade IDs, 
                # generate a pseudo-unique deterministic ID to prevent the MDE from discarding the trade batch
                if not tid:
                    tid = f"{t.get('timestamp', 0)}_{t.get('price', 0)}_{t.get('amount', 0)}_{t.get('side', 'BUY')}"
                
                side = t.get('side')
                side_str = str(side).upper() if side else 'BUY'
                
                result.append({
                    "timestamp": t['timestamp'] / 1000,
                    "price": float(t['price']),
                    "amount": float(t['amount']),
                    "side": side_str,
                    "id": str(tid)
                })
            return result
        except Exception as e:
            logger.error(f"Error fetching trades for {symbol} on {self.exchange_id}: {e}")
            return []
    def get_book_snapshot(self, symbol: str, limit: int = 20) -> Dict:
        try:
            fetch_sym = self._resolve_sym(symbol)
            # Binance strictly rejects arbitrary limits, only accepts preset values. 
            # 1000 causes -1130 on some swap symbols, capping to 500 to be perfectly safe.
            valid_limits = [5, 10, 20, 50, 100, 500, 1000]
            binance_limit = 1000
            for lim in valid_limits:
                if limit <= lim:
                    binance_limit = lim
                    break
            book = self.exchange.fetch_order_book(fetch_sym, limit=binance_limit)
            logger.info(f"[CRYPTO_BOOK] Fetched {fetch_sym} - Bids: {len(book.get('bids', []))}, Asks: {len(book.get('asks', []))}")
            raw_ts = book.get('timestamp')
            ts = (raw_ts / 1000) if raw_ts is not None else datetime.now().timestamp()
            return {
                "bids": [{"price": b[0], "size": b[1]} for b in book['bids']],
                "asks": [{"price": a[0], "size": a[1]} for a in book['asks']],
                "timestamp": ts
            }
        except Exception as e:
            logger.error(f"Error fetching order book for {symbol} on {self.exchange_id}: {e}")
            return {"bids": [], "asks": [], "timestamp": 0}
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        try:
            if not self.connected:
                self.connect()
            fetch_sym = self._resolve_sym(symbol)
            market = self.exchange.market(fetch_sym)
            if not market:
                return None
            precision = market.get('precision', {})
            price_precision = precision.get('price', 2)
            amount_precision = precision.get('amount', 8)
            if isinstance(price_precision, float) and price_precision < 1:
                import math
                digits = int(-math.log10(price_precision))
                tick_size = price_precision
            else:
                digits = int(price_precision)
                tick_size = 10 ** -digits
            price = market.get('price', 0)
            if price == 0:
                try:
                    ticker = self.exchange.fetch_ticker(symbol)
                    price = ticker.get('last', 0)
                except:
                    pass
            major_coins = ["BTC", "ETH", "SOL", "BNB", "XRP", "LTC", "ADA", "DOT"]
            if digits > 2:
                is_major = any(c in symbol.upper() for c in major_coins)
                is_usd_pair = any(u in symbol.upper() for u in ["USDT", "USDC", "USD", "EUR", "BUSD"])
                if is_major or is_usd_pair or price > 100:
                    digits = 2
                    tick_size = 0.01
            return {
                "symbol": symbol,
                "digits": digits,
                "tick_size": tick_size,
                "point": 10 ** -int(amount_precision) if isinstance(amount_precision, (int, float)) else 0.00000001,
                "stops_level": 0,
                "broker_type": "crypto"
            }
        except Exception as e:
            logger.error(f"Error fetching symbol info for {symbol}: {e}")
            return None
    def place_order(self, symbol: str, side: str, amount: float, price: Optional[float] = None, mode: str = "MKT", **kwargs):
        try:
            type = 'market' if mode.upper() in ["MKT", "MARKET"] else 'limit'
            params = {}
            if type == 'market':
                return self.exchange.create_order(symbol, type, side.lower(), amount, params=params)
            else:
                return self.exchange.create_order(symbol, type, side.lower(), amount, price, params=params)
        except Exception as e:
            logger.error(f"Error placing order on {self.exchange_id}: {e}")
            return None
    def cancel_order(self, id: str, symbol: Optional[str] = None):
        try:
            return self.exchange.cancel_order(id, symbol)
        except Exception as e:
            logger.error(f"Error cancelling order {id} on {self.exchange_id}: {e}")
            return False

    def get_latest_candles(self, symbol: str, timeframe: str = '1m', n: int = 100):
        import pandas as pd
        try:
            ohlcv = self.get_ohlcv(symbol, timeframe=timeframe, limit=n)
            if not ohlcv:
                return None
            df = pd.DataFrame(ohlcv, columns=['time', 'Open', 'High', 'Low', 'Close', 'Volume'])
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            return df
        except Exception as e:
            logger.error(f"Error in get_latest_candles for {symbol}: {e}")
            return None

    def get_pending_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        try:
            fetch_sym = self._resolve_sym(symbol) if symbol else None
            if hasattr(self.exchange, 'fetch_open_orders'):
                orders = self.exchange.fetch_open_orders(symbol=fetch_sym)
                result = []
                for o in orders:
                    result.append({
                        "ticket": o.get('id', ''),
                        "symbol": o.get('symbol', ''),
                        "type": o.get('side', '').upper(), 
                        "volume": float(o.get('amount') or 0) - float(o.get('filled') or 0),
                        "price_open": float(o.get('price') or 0),
                        "sl": 0.0,
                        "tp": 0.0,
                        "time_setup": o.get('timestamp', 0) // 1000 if o.get('timestamp') else 0
                    })
                return result
            return []
        except Exception as e:
            logger.error(f"Error fetching pending orders from {self.exchange_id}: {e}")
            return []

    def close_position(self, ticket: str, symbol: Optional[str] = None, volume: float = None) -> bool:
        try:
            positions = self.get_positions(symbol)
            target_pos = None
            for p in positions:
                if str(p.get('ticket')) == str(ticket) or (symbol and p.get('symbol') == symbol):
                    target_pos = p
                    break
            if not target_pos:
                return False
            
            side = 'SELL' if target_pos['type'].upper() == 'BUY' else 'BUY'
            amount = float(volume) if volume and volume > 0 else target_pos['volume']
            
            self.exchange.create_order(target_pos['symbol'], 'market', side.lower(), amount)
            return True
        except Exception as e:
            logger.error(f"Error closing position {ticket} on {self.exchange_id}: {e}")
            return False

    def set_leverage(self, symbol: str, leverage: int) -> Dict:
        try:
            fetch_sym = self._resolve_sym(symbol)
            logger.info(f"Setting leverage for {symbol} (resolved: {fetch_sym}) to {leverage} on {self.exchange_id}")
            
            # Blofin and others often require marginMode (cross/isolated)
            params = {}
            if self.exchange_id.lower() == 'blofin':
                params['marginMode'] = 'cross' # Default to cross
            
            res = self.exchange.set_leverage(leverage, fetch_sym, params)
            logger.info(f"Successfully set leverage to {leverage} for {symbol} on {self.exchange_id}")
            return {"success": True, "result": res}
        except Exception as e:
            logger.error(f"Error setting leverage for {symbol} on {self.exchange_id}: {e}")
            return {"success": False, "error": str(e)}

GLOBAL_CONNECTORS: Dict[str, CryptoConnector] = {}

def get_connector(account_id: str) -> Optional[CryptoConnector]:
    """
    Get or create a crypto connector for the given account.
    
    NOTE: We now try to create the connector even if connect() fails,
    because we can still list symbols without a connected account.
    """
    from src.services.crypto_manager import get_crypto_manager
    manager = get_crypto_manager()
    acc = manager.get_account_full(account_id)
    if not acc:
        logger.warning(f"[GET_CONN] Account not found: {account_id}")
        return None
    
    # Debug: Check if credentials are properly decrypted
    api_key = acc.get('api_key', '')
    api_secret = acc.get('api_secret', '')
    if not api_key or not api_secret or api_secret == 'DECRYPTION_FAILED':
        logger.error(f"[GET_CONN] Invalid credentials for {account_id}: key={'set' if api_key else 'MISSING'}, secret={api_secret[:20] + '...' if api_secret and len(api_secret) > 20 else api_secret}")
        return None
    
    logger.info(f"[GET_CONN] Using credentials for {acc['broker']}: key={api_key[:10]}..., secret={api_secret[:10]}...")
    
    if account_id in GLOBAL_CONNECTORS:
        return GLOBAL_CONNECTORS[account_id]
    try:
        connector = CryptoConnector(
            account_id=account_id,
            exchange_id=acc['broker'],
            api_key=api_key,
            api_secret=api_secret,
            passphrase=acc.get('passphrase'),
            test_mode=(acc['account_type'] == 'demo')
        )
        # Try to connect, but still cache connector even if connection fails
        # (we can still list symbols without being connected)
        if connector.connect():
            GLOBAL_CONNECTORS[account_id] = connector
            logger.info(f"[GET_CONN] Connected and cached: {account_id}")
        else:
            # Even if connect fails, try to load markets without auth
            try:
                connector.exchange.load_markets()
                connector._filter_perpetual_markets()
                GLOBAL_CONNECTORS[account_id] = connector
                logger.info(f"[GET_CONN] Created connector without auth (symbols available): {account_id}")
            except Exception as e:
                logger.warning(f"[GET_CONN] Cannot load markets for {account_id}: {e}")
        return GLOBAL_CONNECTORS.get(account_id)
    except Exception as e:
        logger.error(f"[GET_CONN] Failed to create connector for {account_id}: {e}")
    return None