import ccxt

from src.services.crypto_proxy import apply_proxy
import logging
import threading
import os
import time
import traceback
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
logger = logging.getLogger(__name__)

# File-based debug logger for crypto operations (keeps terminal clean)
_crypto_dbg_logger = None
def _dbg(msg: str):
    """Write debug messages to logs/crypto_debug.log instead of terminal."""
    global _crypto_dbg_logger
    if _crypto_dbg_logger is None:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        _crypto_dbg_logger = logging.getLogger('crypto_debug')
        _crypto_dbg_logger.setLevel(logging.DEBUG)
        _crypto_dbg_logger.propagate = False
        fh = logging.FileHandler(os.path.join(log_dir, 'crypto_debug.log'), mode='a', encoding='utf-8')
        fh.setFormatter(logging.Formatter('%(asctime)s %(message)s', datefmt='%H:%M:%S'))
        _crypto_dbg_logger.addHandler(fh)
    _crypto_dbg_logger.debug(msg)


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
        if self.exchange_id == "bitmex":
            raise ValueError("BitMEX support has been removed")
        self.test_mode = test_mode
        self.connected = False
        self._last_connect_time = 0
        self.passphrase = passphrase
        self.api_key = api_key
        self.api_secret = api_secret
        self._sl_tp_cache = {}  # {symbol: {'sl': float, 'tp': float}}
        
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
        elif self.exchange_id == 'bitmex':
            # BitMEX: Inverse perpetual swaps (BTC/USD:BTC, ETH/USD:ETH, etc.)
            # BitMEX does NOT have USDT-margined products; all are inverse/quanto
            config['options']['defaultType'] = 'swap'
            logger.info(f"[CRYPTO] Initializing BitMEX Perpetuals (INVERSE SWAPS) for {account_id}")

        try:
            exchange_class = getattr(ccxt, self.exchange_id)
            self.exchange = exchange_class(config)
            apply_proxy(self.exchange)
            
            # Suppress fetchOpenOrders warning for Binance
            if self.exchange_id == 'binance':
                self.exchange.options['warnOnFetchOpenOrdersWithoutSymbol'] = False
            
            if test_mode and hasattr(self.exchange, 'urls') and 'test' in self.exchange.urls:
                self.exchange.urls['api'] = self.exchange.urls['test']
                logger.info(f"Using {self.exchange_id} TESTNET")
            
            self._initialized = True
            self._cache = {}
            # DEFAULT TTLs
            self._cache_ttl = 5.0  # Account data TTL (balance, positions)
            self._market_ttl = 0.5 # Market data TTL para Binance/Bybit (500ms)
            self._history_ttl = 60.0 # History TTL
            
            # BitMex tiene límite estricto: 60 req/min → 1 req/s mínimo seguro
            if self.exchange_id == 'bitmex':
                self._cache_ttl = 5.0 
                self._market_ttl = 1.0  # 1 llamada/seg máximo
                self._history_ttl = 600.0
                
            self._acc_lock = threading.Lock()     # Account data lock
            self._mkt_lock = threading.Lock()     # Market data lock (ticks, trades)
            self._history_lock = threading.Lock() # History data lock
            self._ohlcv_lock = threading.Lock()   # Chart data lock
            self._pnl_cache = {"value": 0.0, "ts": 0.0} # PnL Cache
            self._perp_markets = {}
            self._throttled_until = 0.0
            self._sticky_acc_data = {}
            self._sticky_market_data = {}
            self._optimistic_orders = {}
            self._last_market_load = 0.0
            self._last_connect_time = 0.0
            logger.info(f"CryptoConnector initialized for {self.exchange_id} (Account: {account_id})")
        except Exception as e:
            logger.error(f"Failed to initialize ccxt exchange {self.exchange_id}: {e}")
            raise
    
    def _check_throttle(self):
        """Check if we are currently throttled due to rate limits."""
        if time.time() < self._throttled_until:
            return True
        return False

    def _handle_api_error(self, e):
        """Handle CCXT errors and trigger throttling if needed."""
        err_str = str(e).lower()
        if '418' in err_str or '429' in err_str or 'rate limit' in err_str or 'too many requests' in err_str:
            # Throttle for 30 seconds (down from 60s for better recovery)
            self._throttled_until = time.time() + 30.0
            logger.warning(f"[{self.exchange_id}] RATE LIMIT DETECTED. Throttling for 30s. Error: {e}")
            _dbg(f"[{self.exchange_id}] RATE LIMIT: {e}")
        return False

    def connect(self) -> bool:
        if self.connected:
            return True
        
        if self._check_throttle():
            return False
            
        now = time.time()
        if now - self._last_connect_time < 5:
            return False
        
        self._last_connect_time = now
        try:
            # Check if markets already loaded (avoid repeated heavy calls)
            if not self.exchange.markets or (now - self._last_market_load > 3600):
                logger.info(f"Connecting to {self.exchange_id} (Loading Markets, Account: {self.account_id})...")
                self.exchange.load_markets()
                self._filter_perpetual_markets()
                self._last_market_load = now
            else:
                logger.info(f"Using cached markets for {self.exchange_id} (Account: {self.account_id})")
                
            self.connected = True
            return True

        except Exception as e:
            self._handle_api_error(e)
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
        _dbg(f"[{self.exchange_id}] Total markets to filter: {len(self.exchange.markets)}")
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
            
            # Include ALL swap markets (linear and inverse)
            # Most modern exchanges use linear (USDT), but BitMex uses inverse (XBT)
            is_perpetual = (market_type in ['swap', 'future']) or linear or (settle in ['USDT', 'USDC', 'USD', 'BTC', 'XBT', 'ETH'])
            
            # Exclude spot/margin if not explicitly caught by EXCLUDED_MARKET_TYPES
            if market_type == 'spot':
                excluded_count += 1
                continue
            
            if is_perpetual:
                self._perp_markets[sym] = market
            else:
                excluded_count += 1
        
        logger.info(f"[{self.exchange_id}] Filtered markets: {len(self._perp_markets)} perpetual, {excluded_count} excluded")

    def _get_cached_balance(self):
        """Internal helper to get fetch_balance with a very short cache (1s) to avoid redundant hits."""
        now = datetime.now().timestamp()
        if 'fetch_balance' in self._cache:
            entry = self._cache['fetch_balance']
            if now - entry['ts'] < 1.0: # 1 second cache for the raw call
                return entry['data']
        
        try:
            balance = self.exchange.fetch_balance()
            self._cache['fetch_balance'] = {'data': balance, 'ts': now}
            return balance
        except Exception as e:
            self._handle_api_error(e)
            _dbg(f"[{self.exchange_id}] Error in fetch_balance: {e}")
            return {}

    def _clear_acc_cache(self):
        """Invalidates all account-related caches to force a fresh fetch on next poll."""
        keys_to_del = [
            "full_account_snapshot", "full_balance_raw", 
            "snapshot_open_orders"
        ]
        # Also clear all deals_history_* cache entries
        deals_keys = [k for k in self._cache if k.startswith("deals_history")]
        keys_to_del.extend(deals_keys)
        for k in keys_to_del:
            self._cache.pop(k, None)
        # Also reset last fetch timestamp to allow immediate re-fetch
        self._last_acc_fetch = 0
        self._last_mkt_fetch = 0

    def get_account_snapshot(self, date_from: datetime = None) -> Dict:
        now = time.time()
        cache_key = "account_snapshot"
        
        # Check throttle
        if self._check_throttle():
            return self._sticky_acc_data

        if cache_key in self._cache and (now - self._cache[cache_key]['ts'] < self._cache_ttl):
            return self._cache[cache_key]['data']

        # Non-blocking lock for account data
        if not self._acc_lock.acquire(blocking=False):
            return self._sticky_acc_data
            
        try:
                if not self.connected: self.connect()
                if not self.exchange.markets: self.exchange.load_markets()
                
                # 1. Fetch balance (Core data)
                bal_val = 0.0
                equity_val = 0.0
                try:
                    balance = self.exchange.fetch_balance()
                    self._cache['full_balance_raw'] = {'data': balance, 'ts': now}
                    
                    total = balance.get('total', {})
                    info = balance.get('info', {})
                    
                    # Try common assets from unified 'total'
                    bal_val = total.get('USDT', 0.0) or total.get('USDC', 0.0) or total.get('USD', 0.0) or total.get('XBT', 0.0) or total.get('BTC', 0.0)
                    
                    if bal_val == 0.0 and isinstance(info, dict):
                        # Try exchange-specific wallet balance fields (Binance, BitMex, etc.)
                        bal_val = float(info.get('totalWalletBalance', info.get('walletBalance', info.get('marginBalance', 0.0))))
                    
                    equity_val = bal_val
                    if isinstance(info, dict):
                        # Try exchange-specific equity/margin balance fields
                        equity_val = float(info.get('totalMarginBalance', info.get('equity', info.get('marginBalance', bal_val))))
                except Exception as e:
                    logger.debug(f"[{self.exchange_id}] Balance fetch failed: {e}")
                    bal_val = self._sticky_acc_data.get('balance', 0.0)
                    equity_val = self._sticky_acc_data.get('equity', 0.0)

                # BitMex Safety: Small sleep
                if self.exchange_id == 'bitmex': time.sleep(0.2)
                
                # 2. Fetch all positions
                positions_raw = []
                try:
                    positions_raw = self.exchange.fetch_positions()
                except Exception as e:
                    logger.error(f"[{self.exchange_id}] Positions fetch failed: {e}")
                
                # 3. Fetch open orders
                all_open_orders = []
                order_cache_key = "snapshot_open_orders"
                order_ttl = 20.0 if self.exchange_id == 'bitmex' else 5.0
                
                if order_cache_key in self._cache and (now - self._cache[order_cache_key]['ts'] < order_ttl):
                    all_open_orders = self._cache[order_cache_key]['data']
                else:
                    try:
                        if self.exchange_id == 'bitmex': time.sleep(0.2)
                        all_open_orders = self.exchange.fetch_open_orders()
                        self._cache[order_cache_key] = {'data': all_open_orders, 'ts': now}
                    except Exception as e:
                        logger.debug(f"[{self.exchange_id}] Open orders fetch failed: {e}")
                        all_open_orders = self._cache.get(order_cache_key, {}).get('data', [])
                
                # Binance Algo Orders optimization (already cached 5s in get_positions, but we can do it here too)
                all_algo_orders = []
                if self.exchange_id == 'binance':
                    try:
                        algo_cache_key = "binance_all_algo_orders"
                        if algo_cache_key in self._cache and (now - self._cache[algo_cache_key]['ts'] < 5.0):
                            all_algo_orders = self._cache[algo_cache_key]['data']
                        else:
                            import hmac, hashlib, requests
                            algo_params = {'timestamp': int(now * 1000)}
                            query = '&'.join([f"{k}={v}" for k, v in algo_params.items()])
                            signature = hmac.new(self.exchange.secret.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
                            url = f"https://fapi.binance.com/fapi/v1/openAlgoOrders?{query}&signature={signature}"
                            resp = requests.get(url, headers={'X-MBX-APIKEY': self.exchange.apiKey}, timeout=5)
                            if resp.status_code == 200:
                                all_algo_orders = resp.json()
                                self._cache[algo_cache_key] = {'data': all_algo_orders, 'ts': now}
                            else:
                                all_algo_orders = self._cache.get(algo_cache_key, {}).get('data', [])
                    except:
                        all_algo_orders = self._cache.get(algo_cache_key, {}).get('data', [])

                # Realized PNL calculation (today only) - from deals cache if fresh
                realized_pnl = 0.0
                try:
                    # CRITICAL FIX: Use correct cache key (get_deals stores as "deals_history_all")
                    deals_cache = self._cache.get("deals_history_all") or self._cache.get("deals_history_None") or {}
                    if deals_cache and (now - deals_cache.get('ts', 0) < self._history_ttl):
                        # CRITICAL FIX: Only sum deals from TODAY (UTC 00:00), not entire history
                        from datetime import timezone as _tz
                        session_start = datetime.now(_tz.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                        session_start_ts = int(session_start.timestamp())
                        realized_pnl = sum(
                            float(d.get('profit', 0.0))
                            for d in deals_cache.get('data', [])
                            if d.get('time', 0) >= session_start_ts
                        )
                    # else: default to 0.0 — DO NOT use sticky daily_pnl
                    # (it includes floating_pnl, causing runaway accumulation each cycle)
                except:
                    realized_pnl = 0.0

                # Process positions and match orders
                positions = []
                floating_pnl = 0.0
                pending_orders = []

                # Map all open orders to our format
                for o in all_open_orders:
                    pending_orders.append({
                        "id": o.get('id'),
                        "symbol": o.get('symbol'),
                        "type": o.get('type'),
                        "side": o.get('side'),
                        "price": o.get('price'),
                        "amount": o.get('amount'),
                        "status": o.get('status')
                    })

                for p in positions_raw:
                    contracts = float(p.get('contracts') or p.get('positionAmt') or p.get('amount') or 0)
                    if contracts == 0: continue
                    
                    pos_symbol = p.get('symbol')
                    # Standard mapping (similar to get_positions)
                    pos_side = str(p.get('side', '')).upper()
                    if pos_side not in ['LONG', 'SHORT']:
                        amt_signed = float(p.get('info', {}).get('positionAmt', contracts))
                        pos_side = 'SHORT' if amt_signed < 0 else 'LONG'
                    
                    unrealized = float(p.get('unrealizedPnl') or p.get('unRealizedProfit') or p.get('info', {}).get('unRealizedProfit', 0))
                    floating_pnl += unrealized
                    
                    # Find SL/TP for this position from our fetched orders
                    sl = 0.0
                    tp = 0.0
                    
                    # Search in standard open orders
                    binance_sym = pos_symbol.replace('/', '').replace(':USDT', '').replace('-', '').split(':')[0]
                    for o in all_open_orders:
                        o_sym = o.get('symbol')
                        if o_sym == pos_symbol or (self.exchange_id == 'binance' and o_sym.replace('/', '') == binance_sym):
                            o_type = str(o.get('type', '')).upper()
                            stop_px = float(o.get('stopPrice', 0)) or float(o.get('info', {}).get('stopPrice', 0))
                            if stop_px > 0:
                                if 'STOP' in o_type: sl = stop_px
                                elif 'TAKE_PROFIT' in o_type: tp = stop_px
                    
                    # Search in algo orders (Binance)
                    for ao in all_algo_orders:
                        if ao.get('symbol') == binance_sym:
                            stop_px = float(ao.get('triggerPrice', 0))
                            if stop_px > 0:
                                o_type = ao.get('orderType', '').upper()
                                if 'STOP' in o_type: sl = stop_px
                                elif 'TAKE_PROFIT' in o_type: tp = stop_px

                    # Clean symbol for UI compatibility
                    ui_symbol = pos_symbol
                    if self.exchange_id == 'bitmex':
                        if 'XBT' in ui_symbol: ui_symbol = ui_symbol.replace('XBT', 'BTC')
                        if ui_symbol.endswith('USD'): ui_symbol = ui_symbol.replace('USD', '/USDT')
                    if ':' in ui_symbol:
                        ui_symbol = ui_symbol.split(':')[0]

                    positions.append({
                        "symbol": ui_symbol,
                        "type": pos_side,
                        "volume": abs(contracts),
                        "entry_price": float(p.get('entryPrice', p.get('entry_price', 0))),
                        "current_price": float(p.get('markPrice', p.get('mark_price', 0))),
                        "profit": unrealized,
                        "sl": sl,
                        "tp": tp,
                        "ticket": p.get('id') or pos_symbol
                    })

                # Result
                # Apply Optimistic Updates (Fixes "jump-back" effect on SL/TP)
                for p in positions:
                    sym = p['symbol']
                    sl_key = f"SL_{sym}"
                    tp_key = f"TP_{sym}"
                    
                    if sl_key in self._optimistic_orders:
                        opt = self._optimistic_orders[sl_key]
                        if now - opt['ts'] < 10.0:
                            p['sl'] = opt['price']
                        else:
                            del self._optimistic_orders[sl_key]
                            
                    if tp_key in self._optimistic_orders:
                        opt = self._optimistic_orders[tp_key]
                        if now - opt['ts'] < 10.0:
                            p['tp'] = opt['price']
                        else:
                            del self._optimistic_orders[tp_key]

                snapshot = {
                    "balance": float(bal_val),
                    "equity": float(equity_val),
                    "profit": floating_pnl,
                    "positions": positions,
                    "daily_pnl": realized_pnl + floating_pnl,
                    "pending_orders": pending_orders,
                    "timestamp": now
                }
                
                # Cache and update sticky fallback
                self._cache[cache_key] = {'data': snapshot, 'ts': now}
                self._sticky_acc_data.update(snapshot)
                return snapshot
        except Exception as e:
            self._handle_api_error(e)
            logger.error(f"Error fetching account snapshot from {self.exchange_id}: {e}")
            return self._sticky_acc_data
        finally:
            self._acc_lock.release()

    def get_balance(self) -> float:
        now = datetime.now().timestamp()
        cache_key = "balance_val"
        
        # Check throttle
        if self._check_throttle():
            return float(self._sticky_acc_data.get('balance', 0.0))
            
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if now - entry['ts'] < self._cache_ttl:
                return entry['data']

        try:
            snapshot = self.get_account_snapshot()
            return snapshot.get('balance', 0.0)
        except Exception as e:
            logger.error(f"Error fetching balance from {self.exchange_id}: {e}")
            return float(self._sticky_acc_data.get('balance', 0.0))

    def get_equity(self) -> float:
        now = datetime.now().timestamp()
        cache_key = "equity_val"
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if now - entry['ts'] < self._cache_ttl:
                return entry['data']

        try:
            balance = self._get_cached_balance()
            # ALWAYS recalculate equity manually to be sure it includes PNL
            base_balance = self.get_balance()
            positions = self.get_positions()
            unrealized = sum(float(p.get('profit', 0.0)) for p in positions)
            res_equity = base_balance + unrealized
            _dbg(f"[{self.exchange_id}] Equity calculated: {base_balance} + {unrealized} = {res_equity}")
            
            self._cache[cache_key] = {'data': res_equity, 'ts': now}
            return res_equity
        except Exception as e:
            logger.error(f"Error fetching equity from {self.exchange_id}: {e}")
            return self.get_balance()

    def get_deals(self, date_from: Optional[datetime] = None, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch trade history (deals) from the exchange with long caching."""
        now = datetime.now().timestamp()
        # Use symbol in cache key if provided to allow targeted refreshes
        cache_key = f"deals_history_{symbol or 'all'}"
        
        # History is expensive and rarely changes fast. 
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if now - entry['ts'] < self._history_ttl:
                return entry['data']

        if self._check_throttle():
            return self._cache.get(cache_key, {}).get('data', [])

        if not self._history_lock.acquire(blocking=False):
            return self._cache.get(cache_key, {}).get('data', [])
            
        try:
            # Double-check cache inside lock
            if cache_key in self._cache and (now - self._cache[cache_key]['ts'] < self._history_ttl):
                return self._cache[cache_key]['data']

            if not self.connected: self.connect()
            
            trades = []
            since = int(date_from.timestamp() * 1000) if date_from else None
            limit = 1000

            # ── Estrategia de fetch por exchange ──────────────────────────────
            if self.exchange_id == 'binance':
                # Binance Futures NO soporta fetch_my_trades(None) sin símbolo.
                # Intentamos primero con el símbolo solicitado si existe
                symbols_to_try = []
                if symbol:
                    symbols_to_try.append(symbol)
                    # Also try without suffix if it has one
                    if ':' in symbol: symbols_to_try.append(symbol.split(':')[0])
                
                # Intentar fetch_my_trades para los símbolos específicos
                for s in symbols_to_try:
                    try:
                        st = self.exchange.fetch_my_trades(s, since=since, limit=200)
                        if st: trades.extend(st)
                    except: pass
                
                # Build dedup set from fetched trade IDs for O(1) lookup
                fetched_ids = {str(t.get('id', '')) for t in trades if t.get('id')}

                # Siempre intentar income history como base (es lo más fiable para PnL global)
                try:
                    params = {'limit': 1000}
                    if since:
                        params['startTime'] = since
                    income = self.exchange.fapiPrivateGetIncome(params)
                    for entry in income:
                        income_type = entry.get('incomeType', '')
                        if income_type not in ('REALIZED_PNL', 'COMMISSION', 'FUNDING_FEE'):
                            continue
                        # Evitar duplicados si ya los trajimos por fetch_my_trades
                        t_id = entry.get('tradeId') or entry.get('tranId', '')
                        if t_id and str(t_id) in fetched_ids:
                            continue

                        raw_income = float(entry.get('income', 0) or 0)
                        raw_time = int(entry.get('time', 0) or 0)
                        raw_symbol = entry.get('symbol', '') or ''
                        
                        # Inferir side del PnL: ganancia positiva = long cerrado (sell), negativa = short cerrado (buy)
                        # Para comisiones y funding, usar el signo para determinar dirección
                        if income_type == 'REALIZED_PNL':
                            inferred_side = 'sell' if raw_income >= 0 else 'buy'
                        elif income_type == 'COMMISSION':
                            inferred_side = 'sell'  # Comisiones se cobran al cerrar
                        else:
                            inferred_side = 'buy' if raw_income >= 0 else 'sell'
                        
                        # Timestamp: income entries ya vienen en ms
                        ts_ms = raw_time
                        try:
                            dt_str = datetime.fromtimestamp(ts_ms / 1000).isoformat() if ts_ms > 0 else ''
                        except:
                            dt_str = ''

                        trades.append({
                            'id': t_id,
                            'timestamp': ts_ms,
                            'datetime': dt_str,
                            'symbol': raw_symbol,
                            'side': inferred_side,
                            'price': abs(raw_income),  # Usar income como referencia de valor
                            'amount': abs(raw_income),  # Amount = valor del income
                            'fee': {'cost': abs(raw_income) if income_type == 'COMMISSION' else 0,
                                    'currency': entry.get('asset', 'USDT')},
                            'info': entry,
                            '_realized_pnl': raw_income if income_type == 'REALIZED_PNL' else 0,
                            '_income_type': income_type,
                        })
                except Exception as e:
                    logger.warning(f"[binance] fapiPrivateGetIncome failed: {e}")
                    # Fallback final a símbolos comunes si no hay nada
                    if not trades:
                        for sym in ['BTC/USDT:USDT', 'ETH/USDT:USDT']:
                            try:
                                st = self.exchange.fetch_my_trades(sym, since=since, limit=200)
                                if st: trades.extend(st)
                            except: pass

            elif self.exchange_id == 'bitmex':
                # BitMex: intentar con símbolos universales
                main_syms = ['BTC/USD:BTC', 'ETH/USD:ETH', 'XBTUSD']
                if symbol: main_syms.insert(0, symbol)
                for raw_sym in main_syms:
                    resolved = self._resolve_sym(raw_sym) or raw_sym
                    try:
                        st = self.exchange.fetch_my_trades(resolved, since=since, limit=limit)
                        if st:
                            trades.extend(st)
                    except: pass
                # Si aún no hay nada, intentar fetch unificado (a veces funciona)
                if not trades:
                    try:
                        st = self.exchange.fetch_my_trades(None, since=since, limit=limit)
                        if st: trades.extend(st)
                    except: pass

            else:
                # Para el resto (Bybit, OKX, BingX, Bitget, Blofin):
                # fetch_my_trades(None) suele funcionar
                try:
                    all_trades = self.exchange.fetch_my_trades(None, since=since, limit=limit)
                    if all_trades:
                        trades = all_trades
                except Exception as e:
                    logger.warning(f"[{self.exchange_id}] fetch_my_trades(None) failed: {e}")
                    # Fallback símbolo por símbolo con los más comunes
                    for sym in ['BTC/USDT:USDT', 'ETH/USDT:USDT']:
                        resolved = self._resolve_sym(sym)
                        if not resolved: continue
                        try:
                            st = self.exchange.fetch_my_trades(resolved, since=since, limit=100)
                            if st: trades.extend(st)
                        except: pass

            # ── Si no hay nada, NO cachear (para reintentar pronto) ───────────
            if not trades:
                logger.warning(f"[{self.exchange_id}] get_deals: no trades found.")
                return []

            result = []
            seen_tickets = set()
            for t in trades:
                # ── Normalize timestamp (CCXT and income entries use ms) ───────
                t_ts = t.get('timestamp', 0)
                if t_ts is None or t_ts == 0:
                    continue
                # Ensure t_ts is in milliseconds
                if t_ts < 1e10:
                    t_ts = int(t_ts * 1000)  # Was in seconds, convert to ms
                
                try:
                    from datetime import timezone as _tz
                    # Always create trade_time as UTC-aware to avoid naive/aware comparison errors
                    trade_time = datetime.fromtimestamp(t_ts / 1000, tz=_tz.utc)
                except (ValueError, OSError, OverflowError):
                    continue

                if date_from:
                    # Normalize date_from to UTC-aware if it's naive
                    df = date_from
                    from datetime import timezone as _tz
                    if df.tzinfo is None:
                        df = df.replace(tzinfo=_tz.utc)
                    if trade_time < df:
                        continue
                
                # ── Deduplicate ──────────────────────────────────────────────
                ticket = str(t.get('id', ''))
                if ticket and ticket in seen_tickets:
                    continue
                if ticket:
                    seen_tickets.add(ticket)
                
                # ── Income type detection ────────────────────────────────────
                income_type = t.get('_income_type', '')
                
                # Skip COMMISSION entries as standalone deals - they'll be 
                # accounted for in the fee fields of REALIZED_PNL entries
                if income_type == 'COMMISSION':
                    continue
                
                # ── Realized PNL extraction ──────────────────────────────────
                realized_pnl = t.get('_realized_pnl', None)
                if realized_pnl is None:
                    raw_info = t.get('info', {})
                    realized_pnl = 0.0
                    pnl_fields = ['realizedPnl', 'realized_pnl', 'pnl', 'rpnl', 
                                  'realised_pnl', 'realisedPnl', 'real_pnl', 'realized_profit']
                    for f in pnl_fields:
                        if f in raw_info and raw_info[f] is not None:
                            try:
                                realized_pnl = float(raw_info[f])
                                if self.exchange_id == 'bitmex':
                                    realized_pnl = realized_pnl / 100000000.0
                                if realized_pnl != 0: break
                            except: pass
                
                # ── Side inference ───────────────────────────────────────────
                side = t.get('side', '').lower()
                if not side or side not in ('buy', 'sell'):
                    # Infer from PnL sign if no real side provided
                    if realized_pnl > 0:
                        side = 'sell'  # Profitable close = sold position
                    elif realized_pnl < 0:
                        side = 'buy'   # Loss close = bought to cover
                    else:
                        side = 'buy'   # Default for entries
                
                # ── Symbol normalization ──────────────────────────────────────
                trade_sym = t.get('symbol', '')
                if self.exchange_id == 'bitmex':
                    if 'XBT' in trade_sym:
                        trade_sym = trade_sym.replace('XBT', 'BTC')
                    if trade_sym.endswith('USD'):
                        trade_sym = trade_sym.replace('USD', '/USDT')
                if ':' in trade_sym:
                    trade_sym = trade_sym.split(':')[0]
                # Also handle raw Binance format like 'BTCUSDT' -> 'BTC/USDT'
                if trade_sym and '/' not in trade_sym and '-' not in trade_sym:
                    for quote in ['USDT', 'USDC', 'BUSD', 'USD']:
                        if trade_sym.endswith(quote):
                            base = trade_sym[:-len(quote)]
                            if base:
                                trade_sym = f"{base}/{quote}"
                            break
                
                # ── Entry type (IN=0, OUT=1) ────────────────────────────────
                entry_type = 1 if realized_pnl != 0 else 0
                
                # ── Type ID (0=BUY, 1=SELL) ─────────────────────────────────
                type_id = 0 if side == 'buy' else 1
                
                # ── Price: use real price if available, otherwise 0 ──────────
                raw_price = float(t.get('price', 0) or 0)
                raw_amount = float(t.get('amount', 0) or 0)
                
                # For income entries without real price/amount, use safe defaults
                # to prevent NaN in the frontend chart calculations
                if raw_price <= 0 and income_type:
                    raw_price = 0.0  # Will show as 0 in table, not NaN
                if raw_amount <= 0 and income_type:
                    raw_amount = 0.0
                
                # ── Fee extraction ──────────────────────────────────────────
                fee_cost = 0.0
                fee_currency = ""
                fee_obj = t.get('fee')
                if fee_obj:
                    fee_cost = float(fee_obj.get('cost', 0) or 0)
                    fee_currency = fee_obj.get('currency', '')
                
                # ── Time in seconds (LightweightCharts format) ──────────────
                time_seconds = t_ts / 1000.0
                # Round to integer for chart compatibility
                time_seconds = int(time_seconds)
                
                result.append({
                    "ticket": ticket,
                    "symbol": trade_sym,
                    "type": type_id,
                    "volume": raw_amount,
                    "price_open": raw_price, 
                    "price_current": raw_price,
                    "price": raw_price,  # Explicit price field for frontend
                    "profit": float(realized_pnl) if realized_pnl is not None else 0.0,
                    "commission": -abs(fee_cost) if fee_cost > 0 else 0.0,
                    "time": time_seconds,
                    "entry": entry_type,
                    "magic": 0,
                    "swap": 0.0,
                    "comment": f"{income_type + ' | ' if income_type else ''}fee: {fee_cost:.4f} {fee_currency} | {self.exchange_id}"
                })
            
            _dbg(f"[{self.exchange_id}] Fetched {len(result)} trades for history.")
            # Stable sort by time ascending for chart, then by ticket
            final_result = sorted(result, key=lambda x: (x['time'], x['ticket']), reverse=True)
            self._cache[cache_key] = {'data': final_result, 'ts': now}
            return final_result
        except Exception as e:
            logger.error(f"[{self.exchange_id}] Error fetching deals: {e}")
            _dbg(f"[{self.exchange_id}] get_deals FAILED: {e}")
            return []
        finally:
            self._history_lock.release()

    def get_daily_pnl(self) -> float:
        """Calculate realized PNL for the current day (UTC 00:00) + floating PNL."""
        now_ts = time.time()
        # 5 second cache for PnL to avoid hammering get_deals
        if now_ts - self._pnl_cache["ts"] < 5.0:
            return self._pnl_cache["value"]
            
        try:
            from datetime import timezone
            # Calculate session start (UTC 00:00)
            now = datetime.now(timezone.utc)
            session_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # 1. Realized PNL (since session start)
            deals = self.get_deals(date_from=session_start)
            realized = sum(float(d.get('profit', 0.0)) for d in deals)
            
            # 2. Floating PNL
            positions = self.get_positions()
            floating = sum(float(p.get('profit', 0.0)) for p in positions)
            
            val = realized + floating
            self._pnl_cache = {"value": val, "ts": now_ts}
            _dbg(f"[{self.exchange_id}] Daily PNL calculated (Since {session_start} UTC): {realized} (realized) + {floating} (floating) = {val}")
            return val
        except Exception as e:
            _dbg(f"[{self.exchange_id}] Error calculating daily PNL: {e}")
            return self._pnl_cache["value"] if self._pnl_cache["ts"] > 0 else 0.0

    def get_account_info(self) -> Dict[str, Any]:
        snapshot = self.get_account_snapshot()
        # Calculate floating PNL from open positions
        positions = snapshot.get('positions', [])
        floating_pnl = sum(float(p.get('profit', 0.0)) for p in positions)
        return {
            "balance": snapshot.get("balance", 0.0),
            "equity": snapshot.get("equity", 0.0),
            "margin": snapshot.get("margin", 0.0),
            "margin_free": snapshot.get("margin_free", 0.0),
            "margin_level": snapshot.get("margin_level", 0.0),
            "leverage": snapshot.get("leverage", 1.0),
            "currency": "USDT",
            "profit": floating_pnl,
            "daily_pnl": self.get_daily_pnl(),
            "account": self.account_id,
            "name": "Crypto Account",
            "server": self.exchange_id,
            "platform": "crypto"
        }

    def shutdown(self):
        self.connected = False

    def get_current_price(self, symbol: str) -> float:
        now = time.time()
        cache_key = f"current_price_{symbol}"

        # BitMEX is especially sensitive to request bursts; reuse the same
        # short market cache window we already apply to tick data.
        if cache_key in self._cache and (now - self._cache[cache_key]['ts'] < self._market_ttl):
            return float(self._cache[cache_key]['data'])

        try:
            # We use fetch_ticker as it's the fastest way to get current price in CCXT
            fetch_sym = self._resolve_sym(symbol)
            if not fetch_sym:
                return 0.0
            ticker = self.exchange.fetch_ticker(fetch_sym)
            price = float(ticker.get('last') or ticker.get('close') or ticker.get('markPrice') or 0)
            self._cache[cache_key] = {'data': price, 'ts': now}
            self._sticky_market_data[cache_key] = price
            return price
        except Exception as e:
            logger.error(f"[{self.exchange_id}] Error fetching current price for {symbol}: {e}")
            return float(self._sticky_market_data.get(cache_key, 0.0))
    def get_positions(self, symbol: str = None, force_fetch: bool = False) -> List[Dict]:
        """Fetch all open positions (long and short) from the exchange."""
        now = datetime.now().timestamp()
        cache_key = f"positions_{symbol or 'all'}"
        
        # Check throttle
        if self._check_throttle():
            return self._sticky_acc_data.get('positions', [])
            
        if not force_fetch and cache_key in self._cache:
            entry = self._cache[cache_key]
            if now - entry['ts'] < self._cache_ttl:
                return entry['data']

        try:
            snapshot = self.get_account_snapshot()
            all_pos = snapshot.get('positions', [])
            
            if symbol:
                clean_target = symbol.split(':')[0].replace('/', '').replace('-', '').upper()
                return [p for p in all_pos if str(p.get('symbol', '')).split(':')[0].replace('/', '').replace('-', '').upper() == clean_target]
            return all_pos
        except Exception as e:
            logger.error(f"Error fetching positions from {self.exchange_id}: {e}")
            return self._sticky_acc_data.get('positions', [])

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
        # 2. Clean symbol for variations
        clean_sym = symbol.replace("/", "").replace(":", "").replace("_", "").replace("-", "").upper()
        
        # BitMex specific mapping: BTC is XBT
        if self.exchange_id == 'bitmex' and 'BTC' in clean_sym:
            clean_sym = clean_sym.replace('BTC', 'XBT')
            
        # Priority quotes for perpetuals
        quotes = ["USDT", "USDC", "USD"]
        
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

                if self.exchange_id == 'bitmex':
                    # BitMEX perpetuals are usually inverse swaps such as XBTUSD.
                    # Prefer direct inverse variants before the generic crypto ones.
                    bitmex_base = 'XBT' if base == 'XBT' else base
                    perpetual_variants = [
                        f"{bitmex_base}USD",
                        f"{bitmex_base}/USD",
                        f"{bitmex_base}/USD:BTC",
                        f"{bitmex_base}USD:USD",
                    ] + perpetual_variants
                
                for v in perpetual_variants:
                    # Check exact match first
                    if v in markets_to_search:
                        market = markets_to_search[v]
                        if self._is_perpetual_market(market):
                            return v
                    
                    # Check uppercase
                    v_upper = v.upper()
                    if v_upper in markets_to_search:
                        market = markets_to_search[v_upper]
                        if self._is_perpetual_market(market):
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
        
        # 5. GREEDY FALLBACK: Search for any perpetual market that contains the base asset
        # This is for exchanges with very non-standard naming (like BitMex XBTUSD)
        base_asset = clean_sym.replace('USDT', '').replace('USDC', '').replace('USD', '')
        for market_sym, market in markets_to_search.items():
            m_upper = market_sym.upper()
            if base_asset in m_upper and self._is_perpetual_market(market):
                # Extra check for inverse swaps (USD/XBT)
                if 'USD' in m_upper or 'XBT' in m_upper:
                    return market_sym
        
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
        # Modern exchanges use linear, but BitMex uses inverse (settled in BTC/XBT/ETH)
        is_linear_or_inverse = linear or settle in ['USDT', 'USDC', 'USD', 'BTC', 'XBT', 'ETH']
        
        return is_swap_type and is_linear_or_inverse
    def get_tick(self, symbol: str) -> Dict:
        now = time.time()
        cache_key = f"tick_{symbol}"
        
        # Check throttle
        if self._check_throttle():
            return self._sticky_market_data.get(cache_key, {"symbol": symbol, "bid": 0.0, "ask": 0.0, "last": 0.0, "time": now})

        # Short cache for market data to prevent redundant calls
        if cache_key in self._cache and (now - self._cache[cache_key]['ts'] < self._market_ttl):
            return self._cache[cache_key]['data']

        try:
            fetch_sym = self._resolve_sym(symbol)
            ticker = self.exchange.fetch_ticker(fetch_sym)
            result = {
                "symbol": symbol,
                "fetched_symbol": fetch_sym,
                "exchange": self.exchange_id,
                "bid": float(ticker.get('bid', 0) or 0),
                "ask": float(ticker.get('ask', 0) or 0),
                "last": float(ticker.get('last', 0) or 0),
                "baseVolume": float(ticker.get('baseVolume', 0) or 0),
                "quoteVolume": float(ticker.get('quoteVolume', 0) or 0),
                "timestamp": ticker.get('timestamp', 0),
                "time": (ticker.get('timestamp') / 1000) if ticker.get('timestamp') else now
            }
            # Cache result
            self._cache[cache_key] = {'data': result, 'ts': now}
            self._sticky_market_data[cache_key] = result
            return result
        except Exception as e:
            self._handle_api_error(e)
            logger.error(f"Error fetching tick for {symbol} on {self.exchange_id}: {e}")
            return self._sticky_market_data.get(cache_key, {"symbol": symbol, "bid": 0.0, "ask": 0.0, "last": 0.0, "time": now})
    def get_ohlcv(self, symbol: str, timeframe: str = '1m', limit: int = 100) -> List[List]:
        """
        Fetch historical bars with pagination support for large requests.
        """
        now = time.time()
        cache_key = f"ohlcv_{symbol}_{timeframe}_{limit}"
        
        # History is expensive. If limit is large (>1000), cache for 60s. Otherwise 5s.
        history_ttl = 60.0 if limit > 1000 else 5.0
        
        if cache_key in self._cache and (now - self._cache[cache_key]['ts'] < history_ttl):
            return self._cache[cache_key]['data']

        # Check throttle
        if self._check_throttle():
            return self._sticky_market_data.get(cache_key, [])

        try:
            with self._ohlcv_lock:
                # Double check cache inside lock
                if cache_key in self._cache and (now - self._cache[cache_key]['ts'] < history_ttl):
                    return self._cache[cache_key]['data']

                fetch_sym = self._resolve_sym(symbol)
                if not fetch_sym:
                    return []

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
                            tf_ms = self.exchange.parse_timeframe(timeframe) * 1000
                            current_since = ohlcv[0][0] - (batch_limit * tf_ms)
                        else:
                            # Prepend historical bars (ensure no overlaps if the exchange is weird)
                            existing_timestamps = {bar[0] for bar in all_ohlcv}
                            new_bars = [bar for bar in ohlcv if bar[0] not in existing_timestamps]
                            all_ohlcv = new_bars + all_ohlcv

                            # Move 'since' further back
                            tf_ms = self.exchange.parse_timeframe(timeframe) * 1000
                            current_since = ohlcv[0][0] - (batch_limit * tf_ms)

                        remaining -= len(ohlcv)
                        batch_limit = min(remaining, 1000)

                        # If the exchange returned fewer than requested, we might be at the end of available history
                        if len(ohlcv) < 10:
                            break

                    except Exception as e:
                        logger.warning(f"[{self.exchange_id}] Batch fetch failed at iteration {iterations}: {e}")
                        break

                # Sort by timestamp and return the last 'limit' items
                all_ohlcv.sort(key=lambda x: x[0])

                self._cache[cache_key] = {'data': all_ohlcv, 'ts': now}
                self._sticky_market_data[cache_key] = all_ohlcv

                return all_ohlcv[-limit:] if all_ohlcv else []
            
        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol} on {self.exchange_id}: {e}")
            return []
    def get_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        now = time.time()
        cache_key = f"trades_{symbol}"
        
        # Check throttle
        if self._check_throttle():
            return self._sticky_market_data.get(cache_key, [])

        # Short cache
        if cache_key in self._cache and (now - self._cache[cache_key]['ts'] < self._market_ttl):
            return self._cache[cache_key]['data']

        # Non-blocking lock
        if not self._mkt_lock.acquire(blocking=False):
            return self._sticky_market_data.get(cache_key, [])

        try:
            fetch_sym = self._resolve_sym(symbol)
            trades = self.exchange.fetch_trades(fetch_sym, limit=limit)

            result = []
            for t in trades:
                tid = t.get('id')
                if not tid:
                    tid = f"{t.get('timestamp', 0)}_{t.get('price', 0)}_{t.get('amount', 0)}"
                side = t.get('side', 'buy')
                side_str = str(side).upper()

                
                result.append({
                    "timestamp": t['timestamp'] / 1000,
                    "price": float(t['price']),
                    "amount": float(t['amount']),
                    "side": side_str,
                    "id": tid
                })
            
            self._cache[cache_key] = {'data': result, 'ts': now}
            self._sticky_market_data[cache_key] = result
            return result
        except Exception as e:
            self._handle_api_error(e)
            logger.error(f"Error fetching trades for {symbol} on {self.exchange_id}: {e}")
            return self._sticky_market_data.get(cache_key, [])
        finally:
            self._mkt_lock.release()
    def get_book_snapshot(self, symbol: str, limit: int = 20) -> Dict:
        now = time.time()
        cache_key = f"book_{symbol}_{limit}"
        
        # Check throttle
        if self._check_throttle():
            return self._sticky_market_data.get(cache_key, {"bids": [], "asks": [], "timestamp": 0})

        if cache_key in self._cache and (now - self._cache[cache_key]['ts'] < self._market_ttl):
            return self._cache[cache_key]['data']

        # Non-blocking lock for market data
        if not self._mkt_lock.acquire(blocking=False):
            return self._sticky_market_data.get(cache_key, {"bids": [], "asks": [], "timestamp": 0})
            
        try:
            fetch_sym = self._resolve_sym(symbol)
            # Binance strictly rejects arbitrary limits, only accepts preset values.
            # We also keep the limit in the cache key so different depth requests
            # don't incorrectly reuse each other's snapshots.
            valid_limits = [5, 10, 20, 50, 100, 500, 1000]
            binance_limit = 1000
            for lim in valid_limits:
                if limit <= lim:
                    binance_limit = lim
                    break
            book = self.exchange.fetch_order_book(fetch_sym, limit=binance_limit)
            raw_ts = book.get('timestamp')
            ts = (raw_ts / 1000) if raw_ts is not None else datetime.now().timestamp()
            result = {
                "bids": [{"price": b[0], "size": b[1]} for b in book['bids']],
                "asks": [{"price": a[0], "size": a[1]} for a in book['asks']],
                "timestamp": ts
            }
            self._cache[cache_key] = {'data': result, 'ts': now}
            self._sticky_market_data[cache_key] = result
            return result
        except Exception as e:
            self._handle_api_error(e)
            logger.error(f"Error fetching order book for {symbol} on {self.exchange_id}: {e}")
            return self._sticky_market_data.get(cache_key, {"bids": [], "asks": [], "timestamp": 0})
        finally:
            self._mkt_lock.release()
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        try:
            if not self.connected:
                self.connect()
            fetch_sym = self._resolve_sym(symbol)
            if not fetch_sym:
                fetch_sym = symbol
            if self.exchange_id == 'bitmex' and fetch_sym and fetch_sym not in getattr(self.exchange, 'markets', {}):
                # Hard fallback for compact UI tickers that BitMEX never exposes directly.
                sym_up = (symbol or fetch_sym or "").upper().replace('/', '').replace(':', '').replace('-', '')
                if 'BTC' in sym_up:
                    sym_up = sym_up.replace('BTC', 'XBT')
                if sym_up.endswith('USDT') or sym_up.endswith('USD'):
                    fetch_sym = 'XBTUSD'
                elif sym_up.endswith('ETH'):
                    fetch_sym = 'ETHUSD'
            if not fetch_sym:
                return None
            try:
                market = self.exchange.market(fetch_sym)
            except Exception:
                market = getattr(self.exchange, 'markets', {}).get(fetch_sym)
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
                    ticker = self.exchange.fetch_ticker(fetch_sym)
                    price = ticker.get('last', 0)
                except:
                    pass
            major_coins = ["BTC", "ETH", "SOL", "BNB", "XRP", "LTC", "ADA", "DOT"]
            if digits > 2:
                sym_up = (symbol or fetch_sym or "").upper()
                is_major = any(c in sym_up for c in major_coins)
                is_usd_pair = any(u in sym_up for u in ["USDT", "USDC", "USD", "EUR", "BUSD"])
                if is_major or is_usd_pair or price > 100:
                    digits = 2
                    tick_size = 0.01
            return {
                "symbol": symbol or fetch_sym,
                "digits": digits,
                "tick_size": tick_size,
                "point": 10 ** -int(amount_precision) if isinstance(amount_precision, (int, float)) else 0.00000001,
                "stops_level": 0,
                "broker_type": "crypto"
            }
        except Exception as e:
            logger.error(f"Error fetching symbol info for {symbol}: {e}")
            return None
    def get_symbol_details(self, symbol: str) -> Optional[Dict]:
        """
        Returns trading details for a symbol including point_value.
        For crypto perpetuals, point_value = contract_size * current_price per tick.
        Used by live_trade.py for SL/TP risk calculation.
        """
        try:
            fetch_sym = self._resolve_sym(symbol)
            if not fetch_sym:
                return None
            market = self.exchange.market(fetch_sym)
            if not market:
                return None
            contract_size = float(market.get('contractSize', 1.0) or 1.0)
            precision = market.get('precision', {})
            price_precision = precision.get('price', 0.1)
            if isinstance(price_precision, float) and price_precision < 1:
                tick_size = price_precision
            else:
                tick_size = 10 ** -int(price_precision) if price_precision else 0.1
            
            # point_value for perpetual linear contracts (settled in USDT):
            # If price moves $1 and you hold `volume` contracts (in BTC),
            # your PnL changes by $volume. So point_value = 1.0 (linear).
            point_value = 1.0
            
            return {
                "symbol": symbol,
                "contract_size": contract_size,
                "tick_size": tick_size,
                "point_value": point_value,
                "broker_type": "crypto"
            }
        except Exception as e:
            logger.warning(f"[{self.exchange_id}] get_symbol_details error for {symbol}: {e}")
            return None

    def place_order(self, symbol: str, side: str = None, amount: float = None, price: Optional[float] = None, mode: str = "MKT", **kwargs):
        # Handle aliases from OrderGateway
        if side is None and 'order_type' in kwargs:
            side = kwargs.pop('order_type')
        if amount is None and 'volume' in kwargs:
            amount = kwargs.pop('volume')
            
        if side is None or amount is None:
             # Try to find positional args if keywords weren't used correctly
             # (This is a safety net for callers that don't match the new signature)
             logger.error(f"[{self.exchange_id}] place_order called with missing side/amount. kwargs: {kwargs}")
             return None

        if self._check_throttle():
            logger.warning(f"[{self.exchange_id}] Blocking order placement due to active throttle.")
            return None

        resolved_symbol = self._resolve_sym(symbol)
        if self.exchange_id == 'bitmex':
            # BitMEX can receive compact/foreign formats from the UI. Force an
            # inverse perpetual symbol when the resolved value is missing or not
            # a native BitMEX market.
            if not resolved_symbol or resolved_symbol not in getattr(self.exchange, 'markets', {}):
                up = symbol.upper().replace('/', '').replace(':', '').replace('-', '')
                if 'BTC' in up:
                    up = up.replace('BTC', 'XBT')
                if up.startswith('ETH'):
                    resolved_symbol = 'ETHUSD'
                elif up.startswith('XBT') or up.startswith('BTC'):
                    resolved_symbol = 'XBTUSD'
                else:
                    resolved_symbol = 'XBTUSD'
        symbol = resolved_symbol
        try:
            type = 'market' if mode.upper() in ["MKT", "MARKET"] else 'limit'
            params = {}

            # Normalize BitMEX amount to a valid contract quantity.
            if self.exchange_id == 'bitmex':
                try:
                    market = self.exchange.market(symbol)
                except Exception:
                    market = getattr(self.exchange, 'markets', {}).get(symbol, {})
                min_amount = 1.0
                try:
                    min_amount = float((market or {}).get('limits', {}).get('amount', {}).get('min') or 1.0)
                except Exception:
                    min_amount = 1.0
                contract_size = float((market or {}).get('contractSize', 1.0) or 1.0)
                safe_amount = float(amount or 0)
                if safe_amount <= 0:
                    raise ValueError("BitMEX order amount must be greater than 0")
                # If the user sent a small fractional size, interpret it as
                # underlying units and scale to contracts using contractSize.
                if safe_amount < min_amount:
                    if contract_size > 0:
                        safe_amount = safe_amount / contract_size
                    if safe_amount < min_amount:
                        safe_amount = min_amount
                amount = safe_amount
            
            # Extract SL/TP for post-fill placement (Binance doesn't support inline SL/TP)
            sl = kwargs.get('sl')
            tp = kwargs.get('tp')
                
            if type == 'market':
                result = self.exchange.create_order(symbol, type, side.lower(), amount, params=params)
            else:
                result = self.exchange.create_order(symbol, type, side.lower(), amount, price, params=params)
            
            # After main order fills, invalidate position cache and create separate SL/TP stop orders
            if result and (sl or tp):
                _dbg(f"[{self.exchange_id}] [PLACE] Success! ID={result.get('id')}. Triggering BG-MODIFY for SL={sl}, TP={tp}")
                # Invalidate cache so modify_position sees the new position
                for k in list(self._cache.keys()):
                    if 'positions' in k or 'balance' in k:
                        self._cache.pop(k, None)
                
                # Execute modification in background to not block response
                import threading
                def bg_modify():
                    import time
                    _dbg(f"[{self.exchange_id}] [BG-MODIFY] Starting for {symbol} (SL: {sl}, TP: {tp})")
                    for attempt in range(6):
                        time.sleep(2.0 + attempt) # Wait more, then exponential
                        try:
                            _dbg(f"[{self.exchange_id}] [BG-MODIFY] Attempt {attempt+1}/6 for {symbol}")
                            success = self.modify_position(None, sl=sl, tp=tp, symbol=symbol)
                            if success:
                                _dbg(f"[{self.exchange_id}] [BG-MODIFY] Successfully placed SL/TP for {symbol}")
                                return
                            else:
                                _dbg(f"[{self.exchange_id}] [BG-MODIFY] Attempt {attempt+1} failed (modify_position returned False)")
                        except Exception as bg_err:
                            _dbg(f"[{self.exchange_id}] [BG-MODIFY] Error in attempt {attempt+1}: {bg_err}")
                    _dbg(f"[{self.exchange_id}] [BG-MODIFY] Failed after all attempts for {symbol}")
                
                threading.Thread(target=bg_modify, daemon=True).start()
            
            # Invalidate cache so new order shows up immediately
            self._clear_acc_cache()
            return result
        except Exception as e:
            _dbg(f"[{self.exchange_id}] CRITICAL Order Error: {e}")
            logger.error(f"Error placing order on {self.exchange_id}: {e}")
            import traceback
            _dbg(traceback.format_exc())
            return None

    def get_order_size_rules(self, symbol: str) -> Dict[str, float]:
        """
        Return exchange-specific order sizing rules for the resolved market.

        The platform is multi-exchange, so a single generic min_order_size is not
        enough. We prefer the native market metadata when available.
        """
        fetch_sym = self._resolve_sym(symbol)
        market = None
        if fetch_sym:
            try:
                market = self.exchange.market(fetch_sym)
            except Exception:
                market = getattr(self.exchange, 'markets', {}).get(fetch_sym, {})

        market = market or {}
        limits = market.get('limits', {}) or {}
        amount_limits = limits.get('amount', {}) or {}
        precision = market.get('precision', {}) or {}
        contract_size = float(market.get('contractSize', 1.0) or 1.0)

        min_amount = amount_limits.get('min')
        max_amount = amount_limits.get('max')
        step = amount_limits.get('step')
        if step is None:
            amt_prec = precision.get('amount')
            if isinstance(amt_prec, int) and amt_prec >= 0:
                step = 10 ** (-amt_prec)

        return {
            "min_amount": float(min_amount) if min_amount is not None else 0.0,
            "max_amount": float(max_amount) if max_amount is not None else 0.0,
            "step": float(step) if step is not None else 0.0,
            "contract_size": contract_size,
            "resolved_symbol": fetch_sym or symbol,
        }

    def modify_position(self, ticket: Any, sl: float = None, tp: float = None, symbol: str = None) -> bool:
        """
        Sets or updates SL/TP for an open position.
        In Crypto (Binance/Bybit/OKX), SL/TP are usually separate stop orders.
        """
        import time
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                if not self.connected:
                    self.connect()

                # 1. Resolve symbol
                target_symbol = self._resolve_sym(symbol) if symbol else None
                
                # 2. If no symbol provided, try to find it from positions (retry for a few seconds if not found)
                positions = []
                for p_attempt in range(6):
                    # Force fresh fetch - do NOT acquire _acc_lock here as 
                    # get_positions -> get_account_snapshot acquires it internally
                    self._cache.pop("account_snapshot", None)  # Force bypass cache
                    positions = self.get_positions(target_symbol, force_fetch=True)
                        
                    if positions:
                        break
                    _dbg(f"[{self.exchange_id}] Waiting for position to appear (attempt {p_attempt+1}/6)...")
                    time.sleep(1.0)
                
                if not positions:
                    _dbg(f"[{self.exchange_id}] No open position found for {symbol or 'any symbol'}")
                    return False
                
                # For perpetuals, we usually have one position per symbol, 
                # but we should match by ticket if provided to be precise.
                pos = None
                if ticket and str(ticket) not in ["0", "null", "None", ""]:
                    pos = next((p for p in positions if str(p.get('ticket')) == str(ticket)), None)
                
                if not pos:
                    # Fallback to symbol match or first position if symbol was provided
                    pos = positions[0]
                
                target_symbol = pos['symbol']
                
                # 3. Determine side for the exit order (SL/TP)
                # If we are LONG (BUY), SL/TP must be SELL. If SHORT (SELL), SL/TP must be BUY.
                # CCXT returns 'long'/'short' from Binance, not 'buy'/'sell'
                pos_type = str(pos['type']).upper()
                exit_side = 'sell' if pos_type in ('BUY', 'LONG') else 'buy'
                amount = abs(float(pos['volume']))
                
                current_price = float(pos.get('current_price', 0))
                if current_price == 0:
                    current_price = self.get_tick(target_symbol).get('last', 0)
                
                _dbg(f"[{self.exchange_id}] modify_position: pos_type={pos_type}, current_price={current_price}, exit_side={exit_side}, sl={sl}, tp={tp}")
                
                # Hedge mode check for Binance/OKX
                params_base = {'reduceOnly': True}
                raw_info = pos.get('raw_info', {})
                if 'positionSide' in raw_info:
                    params_base['positionSide'] = raw_info['positionSide']
                    # In hedge mode, reduceOnly is often NOT used or implicitly True for the side
                    if self.exchange_id == 'binance':
                        params_base.pop('reduceOnly', None)
                
                # 4. Cancel existing SL/TP orders
                try:
                    open_orders = []
                    try:
                        open_orders = self.exchange.fetch_open_orders(target_symbol)
                    except Exception as e:
                        _dbg(f"[{self.exchange_id}] fetch_open_orders failed: {e}")
                        # If fetch_open_orders fails, we might still want to try fetching all orders or algo orders
                        pass
                    
                    # BINANCE FIX: Fetch Algo Orders too for cancellation
                    if self.exchange_id == 'binance':
                        try:
                            import hmac, hashlib, time, requests
                            binance_symbol = target_symbol.replace('/', '').replace(':USDT', '').replace('-', '').split(':')[0]
                            algo_params = {'symbol': binance_symbol, 'timestamp': int(time.time() * 1000)}
                            query = '&'.join([f"{k}={v}" for k, v in algo_params.items()])
                            signature = hmac.new(self.exchange.secret.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
                            url = f"https://fapi.binance.com/fapi/v1/openAlgoOrders?{query}&signature={signature}"
                            headers = {'X-MBX-APIKEY': self.exchange.apiKey}
                            resp = requests.get(url, headers=headers)
                            if resp.status_code == 200:
                                for ao in resp.json():
                                    open_orders.append({
                                        'id': ao.get('algoId'),
                                        'type': ao.get('orderType', 'STOP_MARKET'),
                                        'stopPrice': float(ao.get('triggerPrice', 0)),
                                        'info': ao,
                                        'is_algo': True
                                    })
                        except Exception as e:
                            _dbg(f"[{self.exchange_id}] Error fetching Algo Orders for cancel: {e}")

                    for o in open_orders:
                        o_type = str(o.get('type', '')).upper()
                        o_id = o.get('id')
                        o_stop = o.get('stopPrice') or o.get('params', {}).get('stopPrice')
                        
                        is_sl_order = 'STOP' in o_type or (o_stop and not 'TAKE' in o_type)
                        is_tp_order = 'TAKE_PROFIT' in o_type or (o_stop and 'TAKE' in o_type)
                        
                        if (sl is not None and is_sl_order) or (tp is not None and is_tp_order):
                            if o.get('is_algo'):
                                _dbg(f"[{self.exchange_id}] Cancelling Algo Order: {o_id}")
                                import hmac, hashlib, time, requests
                                algo_params = {'algoId': o_id, 'timestamp': int(time.time() * 1000)}
                                query = '&'.join([f"{k}={v}" for k, v in algo_params.items()])
                                signature = hmac.new(self.exchange.secret.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
                                url = f"https://fapi.binance.com/fapi/v1/algoOrder?{query}&signature={signature}"
                                headers = {'X-MBX-APIKEY': self.exchange.apiKey}
                                requests.delete(url, headers=headers)
                            else:
                                _dbg(f"[{self.exchange_id}] Cancelling Standard Order: {o_id}")
                                self.exchange.cancel_order(o_id, target_symbol)
                except Exception as e:
                    _dbg(f"[{self.exchange_id}] Cancel error: {e}")
                
                # 5. Create new orders
                amount_prec = float(self.exchange.amount_to_precision(target_symbol, amount)) if hasattr(self.exchange, 'amount_to_precision') else amount

                for sl_tp_type, value in [('SL', sl), ('TP', tp)]:
                    if not value or value <= 0:
                        continue
                    
                    try:
                        val_rounded = float(self.exchange.price_to_precision(target_symbol, value)) if hasattr(self.exchange, 'price_to_precision') else value
                        is_sl = (sl_tp_type == 'SL')
                        
                        # Determine if it's actually an inverse order (e.g. SL above price for LONG is actually a TP)
                        is_inverse = (pos_type in ('BUY', 'LONG') and (val_rounded > current_price if is_sl else val_rounded < current_price)) or \
                                     (pos_type not in ('BUY', 'LONG') and (val_rounded < current_price if is_sl else val_rounded > current_price))
                        
                        if is_sl:
                            o_type = 'TAKE_PROFIT_MARKET' if is_inverse else 'STOP_MARKET'
                        else:
                            o_type = 'STOP_MARKET' if is_inverse else 'TAKE_PROFIT_MARKET'
                            
                        _dbg(f"[{self.exchange_id}] Placing {sl_tp_type} as {o_type} at {val_rounded} (Current: {current_price})")
                        
                        # Standard attempt
                        params = {**params_base, 'stopPrice': val_rounded}
                        try:
                            res = self.exchange.create_order(target_symbol, o_type, exit_side, amount_prec, None, params=params)
                            _dbg(f"[{self.exchange_id}] {sl_tp_type} Order Success: {res.get('id') if isinstance(res, dict) else 'success'}")
                        except Exception as e:
                            if self.exchange_id == 'binance' and ("-4120" in str(e) or "Algo" in str(e)):
                                _dbg(f"[{self.exchange_id}] Standard {o_type} failed. Trying Algo API...")
                                # Fallback to Algo API for Binance
                                try:
                                    import hmac, hashlib, time, requests
                                    # Convert symbol to Binance format (e.g. BTC/USDT:USDT -> BTCUSDT)
                                    binance_symbol = target_symbol.replace('/', '').replace(':USDT', '').replace('.P', '')
                                    
                                    algo_params = {
                                        'symbol': binance_symbol,
                                        'side': exit_side.upper(),
                                        'quantity': amount_prec,
                                        'triggerPrice': val_rounded,
                                        'algoType': 'CONDITIONAL',
                                        'type': o_type,
                                        'timestamp': int(time.time() * 1000)
                                    }
                                    
                                    # Add positionSide if available
                                    if 'positionSide' in params_base:
                                        algo_params['positionSide'] = params_base['positionSide']
                                    else:
                                        algo_params['positionSide'] = 'BOTH' # Default for One-Way
                                        
                                    query = '&'.join([f"{k}={v}" for k, v in algo_params.items()])
                                    signature = hmac.new(self.exchange.secret.encode('utf-8'), query.encode('utf-8'), hashlib.sha256).hexdigest()
                                    
                                    url = f"https://fapi.binance.com/fapi/v1/algoOrder?{query}&signature={signature}"
                                    headers = {'X-MBX-APIKEY': self.exchange.apiKey}
                                    
                                    resp = requests.post(url, headers=headers)
                                    if resp.status_code == 200:
                                        _dbg(f"[{self.exchange_id}] {sl_tp_type} Algo Order Success: {resp.json().get('algoId')}")
                                    else:
                                        _dbg(f"[{self.exchange_id}] {sl_tp_type} Algo Error ({resp.status_code}): {resp.text}")
                                        logger.error(f"[{self.exchange_id}] {sl_tp_type} Algo error: {resp.text}")
                                except Exception as algo_e:
                                    _dbg(f"[{self.exchange_id}] {sl_tp_type} Algo Critical Error: {algo_e}")
                            else:
                                _dbg(f"[{self.exchange_id}] {sl_tp_type} Error: {e}")
                                logger.error(f"[{self.exchange_id}] {sl_tp_type} error: {e}")
                                
                    except Exception as e:
                        _dbg(f"[{self.exchange_id}] {sl_tp_type} Preparation Error: {e}")

                # 6. Update Optimistic State for instant UI feedback
                if sl: self._optimistic_orders[f"SL_{target_symbol}"] = {'price': sl, 'ts': time.time()}
                if tp: self._optimistic_orders[f"TP_{target_symbol}"] = {'price': tp, 'ts': time.time()}
                
                # Invalidate cache immediately
                self._clear_acc_cache()
                return True
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "Too Many Requests" in err_msg:
                    _dbg(f"[{self.exchange_id}] Rate limited in modify_position. Waiting...")
                    time.sleep(1.0 * (attempt + 1))
                else:
                    logger.error(f"[{self.exchange_id}] modify_position critical error on {target_symbol}: {err_msg}")
                    return False
        return False

    def modify_order(self, ticket, price=None, sl=None, tp=None, **kwargs):
        """Modifies a pending order. For most crypto exchanges, this is modify_position logic if it's SL/TP."""
        symbol = kwargs.get('symbol')
        return self.modify_position(ticket, sl, tp, symbol)
    def cancel_order(self, id: str, symbol: Optional[str] = None):
        try:
            res = self.exchange.cancel_order(id, symbol)
            self._clear_acc_cache()
            return res
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

    def get_account_equity(self) -> float:
        try:
            snapshot = self.get_account_snapshot()
            return snapshot.get('equity', 0.0)
        except Exception as e:
            logger.error(f"Error fetching equity from {self.exchange_id}: {e}")
            return float(self._sticky_acc_data.get('equity', 0.0))

    def get_pending_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        now = datetime.now().timestamp()
        cache_key = f"pending_orders_{symbol}" if symbol else "pending_orders_all"
        
        with self._acc_lock:
            if cache_key in self._cache and (now - self._cache[cache_key]['ts'] < self._cache_ttl):
                return self._cache[cache_key]['data']
                
            try:
                fetch_sym = self._resolve_sym(symbol) if symbol else None
                if hasattr(self.exchange, 'fetch_open_orders'):
                    orders = []
                    try:
                        orders = self.exchange.fetch_open_orders(symbol=fetch_sym)
                    except Exception as fe:
                        # If fetching ALL fails (due to weight), try to fetch ONLY for active positions
                        # This is a fallback to save weight
                        if fetch_sym is None:
                            logger.warning(f"[{self.exchange_id}] fetch_open_orders(all) failed, falling back to per-symbol fetch: {fe}")
                            try:
                                # Use cached positions symbols
                                pos_symbols = [p['symbol'] for p in self.get_positions()]
                                for psym in set(pos_symbols):
                                    try:
                                        orders.extend(self.exchange.fetch_open_orders(symbol=psym))
                                    except: pass
                            except: pass
                        else:
                            raise fe

                    result = []
                    # Check for orphan orders if position is already closed
                    pos_symbols = {p['symbol'] for p in self.get_positions()}
                    for o in orders:
                        o_sym = o.get('symbol', '')
                        o_type = o.get('type', '').upper()
                        info = o.get('info', {})
                        is_reduce_only = o.get('reduceOnly') is True or str(info.get('reduceOnly', '')).lower() == 'true' or str(info.get('closePosition', '')).lower() == 'true'
                        
                        if (is_reduce_only or o_type in ['STOP_MARKET', 'TAKE_PROFIT_MARKET', 'STOP', 'TAKE_PROFIT']) and o_sym and o_sym not in pos_symbols:
                            try:
                                logger.info(f"[{self.exchange_id}] Cancelling orphan order {o.get('id')} for {o_sym}")
                                self.exchange.cancel_order(o.get('id'), o_sym)
                                continue
                            except Exception as oe:
                                logger.error(f"[{self.exchange_id}] Failed to cancel orphan order {o.get('id')}: {oe}")

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
                    
                    self._cache[cache_key] = {'data': result, 'ts': now}
                    return result
                
                self._cache[cache_key] = {'data': [], 'ts': now}
                return []
            except Exception as e:
                logger.error(f"Error fetching pending orders from {self.exchange_id}: {e}")
                return []

    def close_position(self, ticket: str, symbol: Optional[str] = None, volume: float = None) -> bool:
        try:
            resolved_sym = self._resolve_sym(symbol) if symbol else None
            positions = self.get_positions(resolved_sym)
            target_pos = None
            for p in positions:
                if str(p.get('ticket')) == str(ticket) or (resolved_sym and p.get('symbol') == resolved_sym):
                    target_pos = p
                    break
            
            # If no match by ticket, just take the first position for that symbol
            if not target_pos and positions:
                target_pos = positions[0]
            
            if not target_pos:
                logger.error(f"[{self.exchange_id}] No position found to close for {symbol}")
                return False
            
            side = 'sell' if target_pos['type'].upper() in ('BUY', 'LONG') else 'buy'
            amount = float(volume) if volume and volume > 0 else target_pos['volume']
            
            # CRITICAL: reduceOnly=True tells Binance this is closing, not opening a new position
            params = {'reduceOnly': True}
            logger.info(f"[{self.exchange_id}] Closing position: {target_pos['symbol']} side={side} amount={amount}")
            self.exchange.create_order(target_pos['symbol'], 'market', side, amount, params=params)
            
            # --- Cleanup conditional orders ---
            try:
                open_orders = self.exchange.fetch_open_orders(target_pos['symbol'])
                for o in open_orders:
                    o_type = o.get('type', '').upper()
                    info = o.get('info', {})
                    is_reduce_only = o.get('reduceOnly') is True or str(info.get('reduceOnly', '')).lower() == 'true' or str(info.get('closePosition', '')).lower() == 'true'
                    if is_reduce_only or o_type in ['STOP_MARKET', 'TAKE_PROFIT_MARKET', 'STOP', 'TAKE_PROFIT']:
                        self.exchange.cancel_order(o.get('id'), target_pos['symbol'])
                        logger.info(f"[{self.exchange_id}] Cancelled conditional order {o.get('id')} for {target_pos['symbol']} after closing position")
            except Exception as oe:
                logger.error(f"[{self.exchange_id}] Failed to cleanup conditional orders for {target_pos['symbol']}: {oe}")
                
            self._clear_acc_cache()
            return True
        except Exception as e:
            logger.error(f"Error closing position {ticket} on {self.exchange_id}: {e}")
            return False

    def set_leverage(self, symbol: str, leverage: int) -> Dict:
        try:
            fetch_sym = self._resolve_sym(symbol)
            if self.exchange_id == 'bitmex' and (not fetch_sym or fetch_sym not in getattr(self.exchange, 'markets', {})):
                up = symbol.upper().replace('/', '').replace(':', '').replace('-', '')
                if 'BTC' in up:
                    up = up.replace('BTC', 'XBT')
                if up.startswith('ETH'):
                    fetch_sym = 'ETHUSD'
                elif up.startswith('XBT') or up.startswith('BTC'):
                    fetch_sym = 'XBTUSD'
                else:
                    fetch_sym = 'XBTUSD'
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

# Keyed by ``(user_id, account_id)``: the credentials behind an account belong to
# one tenant, so a cache hit must never hand one user's authenticated exchange
# session to another whose account happens to share an id.
GLOBAL_CONNECTORS: Dict[Tuple[str, str], CryptoConnector] = {}

def get_connector(account_id: str, *, user_id: str) -> Optional[CryptoConnector]:
    """
    Get or create a crypto connector for one account of one tenant.

    ``user_id`` is a required keyword-only argument. The account row and the key
    that protects its API secret belong to that user; there is no installation-wide
    account and no shared connector.

    NOTE: We now try to create the connector even if connect() fails,
    because we can still list symbols without a connected account.
    """
    from src.services.crypto_manager import get_crypto_manager
    manager = get_crypto_manager()
    acc = manager.get_account_full(account_id, user_id=user_id)
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
    if (acc.get("broker") or "").lower() == "bitmex":
        logger.warning(f"[GET_CONN] BitMEX account blocked: {account_id}")
        return None
    
    cache_key = (user_id, account_id)
    if cache_key in GLOBAL_CONNECTORS:
        return GLOBAL_CONNECTORS[cache_key]
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
            GLOBAL_CONNECTORS[cache_key] = connector
            logger.info(f"[GET_CONN] Connected and cached: {account_id}")
        else:
            # Even if connect fails, try to load markets without auth
            try:
                connector.exchange.load_markets()
                connector._filter_perpetual_markets()
                GLOBAL_CONNECTORS[cache_key] = connector
                logger.info(f"[GET_CONN] Created connector without auth (symbols available): {account_id}")
            except Exception as e:
                logger.warning(f"[GET_CONN] Cannot load markets for {account_id}: {e}")
        return GLOBAL_CONNECTORS.get(cache_key)
    except Exception as e:
        logger.error(f"[GET_CONN] Failed to create connector for {account_id}: {e}")
    return None
