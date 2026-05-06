import asyncio
import threading
import time
import logging
import json
import os
from typing import Optional, List, Dict, Callable, Any
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from .models import (
    FeedStatus, FeedMetrics, MarketDataEvent,
    OrderBookSnapshot, TradeEvent, BookLevel
)
from .buffer import CircularBuffer, SymbolBuffer, TradeBuffer
from src.platform.api.utils import resolve_symbol

logger = logging.getLogger(__name__)


class MarketDataEngine:
    _instance: Optional['MarketDataEngine'] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, platform: str = "mt5", config_path: str = None):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        self._platform = platform
        self._config_path = config_path
        self._status = FeedStatus.OFFLINE
        self._metrics = FeedMetrics()
        self._running = False
        self._starting = False
        self._should_stop = threading.Event()

        # ── Buffers ──────────────────────────────────────────────────────────
        self._event_buffer  = CircularBuffer(max_size=50000)
        self._symbol_buffer = SymbolBuffer(history_size=5000)
        self._trade_buffer  = TradeBuffer(max_size=10000)

        # ── Symbol registry ───────────────────────────────────────────────────
        self._symbols: set = set()
        self._symbols_lock = threading.RLock()
        self._symbol_depths: Dict[str, int] = {}

        # ── Persistent order-book cache ───────────────────────────────────────
        self._persistent_books: Dict[str, Dict] = {}
        self._pb_lock = threading.Lock()

        # ── Connectors ────────────────────────────────────────────────────────
        self._connectors: Dict[str, Any] = {}
        self._connector_lock = threading.Lock()
        self._mt5_connect_path = None

        # ── Thread pool / feed thread ─────────────────────────────────────────
        self._executor    = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mde_worker")
        self._feed_thread: Optional[threading.Thread] = None
        self._status_callbacks: List[Callable[[FeedStatus], None]] = []

        # ── MT5 tick-level state ──────────────────────────────────────────────
        # _last_tick_time   : last processed tick timestamp (ms) per symbol
        # _last_abs_volume  : last raw cumulative volume reading per symbol
        # _last_quote_cache : dedup key for tick emission per symbol
        self._last_tick_time:   Dict[str, float] = {}
        self._last_abs_volume:  Dict[str, float] = {}
        self._last_quote_cache: Dict[str, str]   = {}
        self._last_bid:         Dict[str, float] = {}
        self._last_ask:         Dict[str, float] = {}

        # FIX (BUG 4,5,7): dedicated per-candle delta/volume accumulators for MT5
        # Keyed by symbol_upper. Reset whenever the candle bar timestamp changes.
        self._mt5_delta_acc:   Dict[str, float] = {}   # accumulated delta for current bar
        self._mt5_vol_acc:     Dict[str, float] = {}   # accumulated volume for current bar
        self._mt5_bar_ts:      Dict[str, int]   = {}   # open-timestamp of current bar (seconds)

        # ── Crypto state ──────────────────────────────────────────────────────
        self._crypto_seen_trade_ids:    Dict[str, set]  = {}
        # FIX (BUG 2,3): track which candle bar the accumulators belong to
        self._crypto_delta_acc:         Dict[str, float] = {}
        self._crypto_volume_acc:        Dict[str, float] = {}
        self._crypto_delta_bar_ts:      Dict[str, int]   = {}  # bar open ts (seconds)
        self._last_crypto_candle_poll:  Dict[str, float] = {}
        self._last_crypto_trade_poll:   Dict[str, float] = {}
        self._last_crypto_book_poll_strict: Dict[str, float] = {}
        self._crypto_last_emitted_ohlcv_ts: Dict[str, int]   = {}  # Track last closed bar emitted
        self._crypto_connector_cache:      Dict[str, Any]   = {}  # Cache: symbol_upper -> connector_instance

        # ── Live candle cache (built from trades between OHLCV polls) ─────────
        # Keyed by symbol_upper. Each value: {open, high, low, close}
        self._crypto_live_candle:  Dict[str, Dict[str, float]] = {}
        self._last_crypto_ticker_poll: Dict[str, float] = {}  # Fast ticker poll timing

        # ── Polling intervals ─────────────────────────────────────────────────
        # CRITICAL FIX: Changed from 25ms to 50ms for better stability
        # Crypto exchanges have ~200-2000ms API latency, 25ms was too aggressive
        self._poll_interval_ms    = 50
        self._book_interval_ms    = 100
        self._last_book_poll:     Dict[str, float] = {}
        self._reconnect_delay_s   = 5
        self._max_reconnect_attempts = 10
        self._latency_threshold_ms   = 50
        self._last_candle_poll: float = 0.0

        self._setup_logging()
        logger.info(f"MarketDataEngine inicializado para plataforma: {platform}")

    # ─────────────────────────────────────────────────────────────────────────
    # Logging
    # ─────────────────────────────────────────────────────────────────────────

    def _setup_logging(self):
        log_dir = os.path.join(os.path.dirname(__file__), "../../../logs")
        os.makedirs(log_dir, exist_ok=True)
        json_handler = logging.FileHandler(
            os.path.join(log_dir, "market_data_engine.log"),
            encoding='utf-8'
        )
        json_handler.setLevel(logging.DEBUG)

        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_entry = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "level":     record.levelname,
                    "service":   "market-data-engine",
                    "message":   record.getMessage(),
                    "module":    record.module,
                    "function":  record.funcName
                }
                if hasattr(record, 'extra'):
                    log_entry.update(record.extra)
                return json.dumps(log_entry)

        json_handler.setFormatter(JsonFormatter())
        logger.addHandler(json_handler)
        logger.setLevel(logging.DEBUG)

    # ─────────────────────────────────────────────────────────────────────────
    # Connector management
    # ─────────────────────────────────────────────────────────────────────────

    def _get_connector(self, platform: str = None):
        p = platform or self._platform
        with self._connector_lock:
            if p not in self._connectors or (
                p == "crypto" and self._connectors[p] is None
            ):
                if p == "mt5":
                    from src.live.connector import get_mt5_connector
                    self._connectors[p] = get_mt5_connector()

                elif p == "crypto":
                    from src.services.crypto_manager import get_crypto_manager
                    from src.live.crypto_connector import get_connector
                    try:
                        manager  = get_crypto_manager()
                        accounts = manager.get_accounts()
                        master   = next(
                            (acc for acc in accounts if acc.get("is_master")), None
                        ) or (accounts[0] if accounts else None)
                        if master:
                            self._connectors[p] = get_connector(master["id"])
                            logger.info(
                                f"MarketDataEngine connected to Crypto via account {master['id']}"
                            )
                        else:
                            self._connectors[p] = None
                    except Exception as e:
                        logger.error(f"Error initializing Crypto connector in MDE: {e}")
                        self._connectors[p] = None

                elif p == "tradovate":
                    from src.services.tradovate_manager import get_tradovate_manager
                    from src.live.tradovate_connector import get_tradovate_connector
                    try:
                        manager  = get_tradovate_manager()
                        accounts = manager.get_accounts()
                        master   = next(
                            (acc for acc in accounts if acc.get("is_master")), None
                        ) or (accounts[0] if accounts else None)
                        if master:
                            self._connectors[p] = get_tradovate_connector(master["id"])
                            logger.info(
                                f"MarketDataEngine connected to Tradovate via account {master['id']}"
                            )
                        else:
                            self._connectors[p] = None
                    except Exception as e:
                        logger.error(f"Error initializing tradovate connector: {e}")
                        self._connectors[p] = None

                else:
                    raise ValueError(
                        f"Plataforma no soportada: {p}. Soportados: MT5, Crypto, Tradovate."
                    )

            return self._connectors[p]

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def start(self) -> bool:
        if self._running:
            return True
        if self._starting:
            return False
        self._starting = True
        start_time = time.time()
        print("MDE_START: [1/4] Iniciando MarketDataEngine...")
        self._should_stop.clear()
        self._update_status(FeedStatus.CONNECTING)
        try:
            print(f"MDE_START: [2/4] Obteniendo conector para {self._platform}...")
            connector      = self._get_connector(self._platform)
            connect_kwargs = {}
            if self._platform == "mt5":
                try:
                    from src.services.mt5_launcher import get_launcher
                    launcher = get_launcher()
                    if launcher.mt5_exe:
                        connect_kwargs['path'] = launcher.mt5_exe
                        self._mt5_connect_path  = launcher.mt5_exe
                        print(f"MDE_START: Usando MT5 en {launcher.mt5_exe}")
                except Exception as e:
                    logger.warning(f"No se pudo obtener path del launcher: {e}")

            print(f"MDE_START: [3/4] Llamando a connector.connect({self._platform})...")
            if not connector.connect(**connect_kwargs):
                print(
                    f"MDE_START: WARNING - Fallo en conexión {self._platform}. "
                    "Se reintentará en el loop."
                )
                self._update_status(FeedStatus.DEGRADED)
            else:
                print(f"MDE_START: Conexión {self._platform} establecida con éxito.")
                self._update_status(FeedStatus.ONLINE)

            self._running  = True
            self._starting = False
            self._metrics.connected_since = (
                time.time() if self._status == FeedStatus.ONLINE else 0
            )

            self._feed_thread = threading.Thread(
                target=self._feed_loop,
                name="MDE_FeedLoop",
                daemon=True
            )
            self._feed_thread.start()
            elapsed = (time.time() - start_time) * 1000
            logger.info(f"MarketDataEngine iniciado en {elapsed:.0f}ms")
            return True

        except Exception as e:
            logger.error(f"Error iniciando MarketDataEngine: {e}")
            self._update_status(FeedStatus.OFFLINE)
            self._starting = False
            return False

    def stop(self) -> None:
        if not self._running:
            return
        logger.info("Deteniendo MarketDataEngine...")
        self._should_stop.set()
        self._running = False
        if self._feed_thread and self._feed_thread.is_alive():
            self._feed_thread.join(timeout=5.0)
        with self._connector_lock:
            for p, conn in self._connectors.items():
                try:
                    print(f"MDE_STOP: Desconectando {p}...")
                    if conn and hasattr(conn, 'shutdown'):
                        conn.shutdown()
                except Exception:
                    pass
            self._connectors = {}
        self._update_status(FeedStatus.OFFLINE)
        logger.info("MarketDataEngine detenido")

    # ─────────────────────────────────────────────────────────────────────────
    # Subscription
    # ─────────────────────────────────────────────────────────────────────────

    def _is_crypto_symbol(self, symbol: str) -> bool:
        """Check if a symbol is a crypto perpetual symbol."""
        s = symbol.upper()
        crypto_patterns = ['USDT', 'USDC', '/USDT', ':USDT', '/USDC', ':USDC', 'BTC', 'ETH']
        return any(p in s for p in crypto_patterns)

    def _normalize_symbol_for_subscription(self, symbol: str) -> str:
        """
        CRITICAL FIX: Normalize symbols for perpetual futures trading.
        
        Rules:
        - BTC/USDT:USDT -> BTC/USDT:USDT (keep perpetual format)
        - BTC/USDT -> BTC/USDT:USDT (add :USDT for perpetuals)
        - BTC/USDT/USDT -> BTC/USDT:USDT (normalize to perpetual format)
        - For MT5/forex: keep as-is
        """
        original = symbol
        symbol = symbol.upper().strip()
        
        # Check if this is a crypto symbol
        is_crypto = self._is_crypto_symbol(symbol)
        
        # Handle crypto perpetual symbols
        if is_crypto:
            # Remove any existing : suffix for re-formatting
            if ':' in symbol:
                base = symbol.split(':')[0]
                symbol = base
            
            # If symbol has /USDT or /USDC, add the : suffix for perpetual format
            # This is how exchanges represent perpetual contracts: BTC/USDT:USDT
            if '/USDT' in symbol and ':' not in symbol:
                symbol = f"{symbol}:USDT"
            elif '/USDC' in symbol and ':' not in symbol:
                symbol = f"{symbol}:USDC"
            elif '/USD' in symbol and ':' not in symbol:
                symbol = f"{symbol}:USD"
            
            # Handle BTCUSDT style (no slash)
            clean = symbol.replace('/', '').replace(':', '')
            if clean.endswith('USDT') and '/' not in symbol and ':' not in symbol:
                base = clean[:-4]
                symbol = f"{base}/USDT:USDT"
            elif clean.endswith('USDC') and '/' not in symbol and ':' not in symbol:
                base = clean[:-4]
                symbol = f"{base}/USDC:USDC"
        
        # Handle MT5/forex symbols - keep as-is
        else:
            # Remove duplicate suffixes for non-crypto
            if '/USDT' in symbol and symbol.endswith(':USDT'):
                symbol = symbol.replace(':USDT', '')
            elif '/USDC' in symbol and symbol.endswith(':USDC'):
                symbol = symbol.replace(':USDC', '')
            
            # If symbol has multiple slashes, normalize to first pair
            parts = symbol.split('/')
            if len(parts) >= 3:
                symbol = f"{parts[0]}/{parts[1]}"
        
        return symbol

    def subscribe(self, symbols: List[str]) -> None:
        # FIX (BUG 8): always use the symbols_lock when mutating _symbols
        # CRITICAL FIX: Normalize symbols to prevent duplicates like BTC/USDT:USDT
        with self._symbols_lock:
            for symbol in symbols:
                original = symbol
                symbol = self._normalize_symbol_for_subscription(symbol)
                
                # Check if normalized symbol already exists (as different variant)
                existing_match = None
                for existing in self._symbols:
                    if self._normalize_symbol_for_subscription(existing) == symbol:
                        existing_match = existing
                        break
                
                if existing_match:
                    if original != existing_match:
                        logger.info(f"[SYMBOL_DEDUP] Ignoring duplicate subscription '{original}' (already subscribed as '{existing_match}')")
                    continue
                        
                if symbol not in self._symbols:
                    self._symbols.add(symbol)
                    logger.info(f"Suscrito a símbolo: {symbol}")
            self._metrics.symbols_subscribed = list(self._symbols)

    def unsubscribe(self, symbols: List[str]) -> None:
        with self._symbols_lock:
            for symbol in symbols:
                symbol = symbol.upper()
                if symbol in self._symbols:
                    self._symbols.remove(symbol)
                    logger.info(f"Desuscrito de símbolo: {symbol}")
            self._metrics.symbols_subscribed = list(self._symbols)

    def switch_platform(self, new_platform: str) -> bool:
        if new_platform not in ["mt5", "crypto", "tradovate"]:
            logger.error(f"Cannot switch to unsupported platform: {new_platform}")
            return False
        if new_platform == self._platform and self._status == FeedStatus.ONLINE:
            return True
        logger.info(f"Switching engine platform: {self._platform} -> {new_platform}")
        self._update_status(FeedStatus.OFFLINE)
        with self._connector_lock:
            for p, conn in self._connectors.items():
                try:
                    if conn and hasattr(conn, 'shutdown'):
                        conn.shutdown()
                except Exception as e:
                    logger.warning(f"Error disconnecting previous connector {p}: {e}")
            self._connectors = {}
        self._metrics = FeedMetrics()
        self._platform = new_platform
        self._clear_buffers()
        self._get_connector(new_platform)
        return self._try_reconnect()

    def _clear_buffers(self):
        self._event_buffer.clear()
        self._symbol_buffer.clear()
        self._trade_buffer.clear()
        # Reset all per-symbol accumulators
        self._last_tick_time.clear()
        self._last_abs_volume.clear()
        self._last_quote_cache.clear()
        self._mt5_delta_acc.clear()
        self._mt5_vol_acc.clear()
        self._mt5_bar_ts.clear()
        self._crypto_seen_trade_ids.clear()
        self._crypto_delta_acc.clear()
        self._crypto_volume_acc.clear()
        self._crypto_delta_bar_ts.clear()
        self._last_crypto_candle_poll.clear()
        self._crypto_live_candle.clear()
        logger.info("Buffers and accumulators cleared")

    # ─────────────────────────────────────────────────────────────────────────
    # Feed loop
    # ─────────────────────────────────────────────────────────────────────────

    def _feed_loop(self) -> None:
        reconnect_attempts   = 0
        last_reconnect_attempt = 0
        while not self._should_stop.is_set():
            try:
                if self._status in (FeedStatus.OFFLINE, FeedStatus.RECONNECTING):
                    now = time.time()
                    if now - last_reconnect_attempt > self._reconnect_delay_s:
                        last_reconnect_attempt = now
                        if reconnect_attempts < self._max_reconnect_attempts:
                            self._update_status(FeedStatus.RECONNECTING)
                            if self._try_reconnect():
                                reconnect_attempts = 0
                                self._update_status(FeedStatus.ONLINE)
                            else:
                                reconnect_attempts += 1
                                self._update_status(FeedStatus.DEGRADED)
                        else:
                            logger.error("Máximo de intentos de reconexión alcanzado, reseteando...")
                            reconnect_attempts = 0
                            self._update_status(FeedStatus.DEGRADED)

                poll_start = time.time()
                with self._symbols_lock:
                    current_symbols = list(self._symbols)

                for symbol in current_symbols:
                    self._poll_symbol(symbol)

                poll_duration = (time.time() - poll_start) * 1000
                sleep_time    = max(0, (self._poll_interval_ms - poll_duration) / 1000)
                if sleep_time > 0:
                    time.sleep(sleep_time)

            except Exception as e:
                logger.error(f"Error en feed loop: {e}")
                self._metrics.errors_count += 1
                if self._status == FeedStatus.ONLINE:
                    self._update_status(FeedStatus.DEGRADED)
                time.sleep(1)

    # ─────────────────────────────────────────────────────────────────────────
    # Poll dispatcher
    # ─────────────────────────────────────────────────────────────────────────

    def _poll_symbol(self, symbol: str) -> None:
        """
        CRITICAL FIX: Added symbol-level error tracking to prevent failing symbols
        from saturating the entire engine.
        """
        poll_start = time.time()
        now        = poll_start
        s_upper    = symbol.upper()
        
        # Initialize error tracking if not exists
        if not hasattr(self, '_symbol_error_count'):
            self._symbol_error_count: Dict[str, int] = {}
        if not hasattr(self, '_symbol_last_success'):
            self._symbol_last_success: Dict[str, float] = {}

        last_book      = self._last_book_poll.get(s_upper, 0)
        should_poll_book = (now - last_book) >= (self._book_interval_ms / 1000.0)
        if should_poll_book:
            self._last_book_poll[s_upper] = now

        try:
            target_platform = self._detect_platform(symbol)
            
            # CRITICAL FIX: Skip symbols with too many consecutive errors
            # This prevents a failing symbol (like old MT5 subscriptions) from saturating the engine
            error_count = self._symbol_error_count.get(s_upper, 0)
            last_success = self._symbol_last_success.get(s_upper, 0)
            
            if error_count >= 10:
                # Symbol has failed 10+ times consecutively - skip it
                # Only poll it once every 60 seconds to check if it's recovered
                if now - last_success > 60:
                    logger.warning(f"[MDE_SKIP] Symbol {symbol} skipped (too many errors), will retry in 60s")
                    self._symbol_error_count[s_upper] = 0  # Reset to try again
                return
            
            # CRITICAL FIX: For crypto, use the symbol directly as broker_symbol
            # The connector's _resolve_sym will handle the perpetual format
            # We don't use resolve_symbol() from utils.py for crypto - it only handles MT5
            if target_platform == "crypto":
                broker_symbol = symbol  # Use the normalized symbol directly
            else:
                broker_symbol = resolve_symbol(symbol)
            
            if should_poll_book:
                logger.debug(f"[MDE_POLL] Symbol={symbol} Platform={target_platform} BrokerSym={broker_symbol}")

            if target_platform == "crypto":
                self._poll_crypto_symbol(symbol, broker_symbol, should_poll_book)
                # Mark success
                self._symbol_error_count[s_upper] = 0
                self._symbol_last_success[s_upper] = now
                return

            connector = self._get_connector(target_platform)
            if not connector:
                if should_poll_book:
                    logger.warning(f"[MDE_WARN] No connector for platform {target_platform} (symbol {symbol})")
                self._symbol_error_count[s_upper] = self._symbol_error_count.get(s_upper, 0) + 1
                return

            self._poll_mt5_symbol(
                symbol, s_upper, broker_symbol, connector, should_poll_book
            )
            # Mark success
            self._symbol_error_count[s_upper] = 0
            self._symbol_last_success[s_upper] = now

        except Exception as e:
            logger.error(f"Error polling símbolo {symbol}: {e}")
            self._metrics.errors_count += 1
            self._symbol_error_count[s_upper] = self._symbol_error_count.get(s_upper, 0) + 1
        finally:
            total_poll_time = (time.time() - poll_start) * 1000
            if total_poll_time > 250:
                logger.warning(
                    f"HIGH_POLL_LATENCY: {symbol} took {total_poll_time:.1f}ms"
                )

    # ─────────────────────────────────────────────────────────────────────────
    # MT5 polling
    # ─────────────────────────────────────────────────────────────────────────

    def _poll_mt5_symbol(
        self,
        symbol: str,
        s_upper: str,
        broker_symbol: str,
        connector,
        should_poll_book: bool
    ) -> None:
        tick_start = time.time()

        # ── 1. Fetch and process recent ticks ────────────────────────────────
        # FIX (BUG 4,5): accumulate delta/volume per candle bar (not per minute)
        accumulated_delta = self._mt5_delta_acc.get(s_upper, 0.0)
        accumulated_vol   = self._mt5_vol_acc.get(s_upper, 0.0)

        try:
            last_processed_ts = self._last_tick_time.get(s_upper, 0)
            ticks_df = None

            if last_processed_ts > 0 and hasattr(connector, 'get_ticks_since'):
                ticks_df = connector.get_ticks_since(broker_symbol, last_processed_ts)
            if ticks_df is None:
                n_ticks  = 2000 if last_processed_ts == 0 else 100
                if hasattr(connector, 'get_recent_ticks'):
                    ticks_df = connector.get_recent_ticks(broker_symbol, n=n_ticks)

            if ticks_df is not None and not ticks_df.empty:
                is_future = any(
                    x in s_upper for x in
                    ["MES", "MNQ", "ES", "NQ", "CL", "GC", "RTY", "YM", "FDAX", "FESX"]
                )
                use_real = 'volume_real' in ticks_df.columns
                v_col    = (
                    'volume_real'
                    if use_real and (is_future or ticks_df['volume_real'].sum() > 0)
                    else 'volume'
                )
                ts_col      = 'time_msc' if 'time_msc' in ticks_df.columns else 'time'
                max_tick_ts = float(ticks_df[ts_col].max())

                if max_tick_ts > last_processed_ts:
                    self._last_tick_time[s_upper] = max_tick_ts

                trade_batch   = []
                ticks_list    = ticks_df.to_dict('records')
                batch_buy_vol = 0.0
                batch_sell_vol = 0.0

                # Prime Bid/Ask cache with current tick info to ensure accurate side detection
                try:
                    curr_tick = connector.get_current_tick(broker_symbol)
                    if curr_tick:
                        if hasattr(curr_tick, 'bid') and curr_tick.bid > 0: self._last_bid[s_upper] = curr_tick.bid
                        if hasattr(curr_tick, 'ask') and curr_tick.ask > 0: self._last_ask[s_upper] = curr_tick.ask
                except Exception as e:
                    logger.debug(f"Error priming tick cache for {symbol}: {e}")

                for tick in ticks_list:
                    t_ts = float(tick.get(ts_col, 0))
                    if t_ts <= last_processed_ts:
                        continue

                    raw_v  = float(tick.get('volume_real') or tick.get('volume') or 0)
                    prev_v = self._last_abs_volume.get(s_upper, 0)
                    flags  = tick.get('flags', 0)

                    # Accumulators will be updated after t_side is determined

                    # MT5 volume_real/volume is per-tick, not cumulative.
                    # Using it directly as the trade volume ensures all trades are captured.
                    t_vol = raw_v
                    self._last_abs_volume[s_upper] = raw_v

                    # Update quote cache for side detection fallback
                    t_bid = float(tick.get('bid', 0))
                    t_ask = float(tick.get('ask', 0))
                    if t_bid > 0: self._last_bid[s_upper] = t_bid
                    if t_ask > 0: self._last_ask[s_upper] = t_ask

                    t_side = ""
                    if flags & 32: # TICK_FLAG_BUY
                        t_side = "BUY"
                    elif flags & 64: # TICK_FLAG_SELL
                        t_side = "SELL"
                    
                    # Fallback for side detection if flags are missing or inconsistent
                    if not t_side and t_vol > 0:
                        last = float(tick.get('last', 0))
                        # Use current tick quote if available, else use cached
                        curr_ask = t_ask if t_ask > 0 else self._last_ask.get(s_upper, 0)
                        curr_bid = t_bid if t_bid > 0 else self._last_bid.get(s_upper, 0)
                        
                        if curr_ask > 0 and last >= curr_ask:
                            t_side = "BUY"
                        elif curr_bid > 0 and last <= curr_bid:
                            t_side = "SELL"
                        elif curr_ask > 0 and curr_bid > 0:
                            mid = (curr_ask + curr_bid) / 2
                            t_side = "BUY" if last >= mid else "SELL"
                        else:
                            # If no quote info at all, default based on last known side or BUY as safe default
                            t_side = "BUY"

                    if t_vol > 0 and t_side:
                        # Update batch accumulators for session delta calculation
                        if t_side == "BUY":
                            batch_buy_vol += t_vol
                        else:
                            batch_sell_vol += t_vol

                        ts_val = (
                            float(tick['time_msc'] / 1000)
                            if 'time_msc' in tick
                            else float(tick['time'])
                        )
                        p = float(tick['last'])
                        # Debug trade detection
                        if t_vol > 0:
                            logger.info(f"[MDE_TRADE] {symbol} {t_side} Vol={t_vol} Price={p} Flags={flags}")

                        trade_ev = MarketDataEvent(
                            symbol=symbol, timestamp=ts_val, event_type="TRADE",
                            last=p, last_size=t_vol, side=t_side, source="MT5",
                            flags=flags
                        )
                        trade_batch.append(trade_ev)
                        self._trade_buffer.push(TradeEvent(
                            symbol=symbol, timestamp=ts_val,
                            price=p, size=t_vol, side=t_side
                        ))

                if trade_batch:
                    self._event_buffer.push_batch(trade_batch)

                # FIX (BUG 4,5): accumulate batch delta into per-candle accumulator
                accumulated_delta += (batch_buy_vol - batch_sell_vol)
                accumulated_vol   += (batch_buy_vol + batch_sell_vol)
                self._mt5_delta_acc[s_upper] = accumulated_delta
                self._mt5_vol_acc[s_upper]   = accumulated_vol

        except Exception as e:
            logger.debug(f"Error processing ticks for {symbol}: {e}")

        # ── 2. Emit TICK event ────────────────────────────────────────────────
        if hasattr(connector, 'get_current_price'):
            price = connector.get_current_price(broker_symbol)
            if price:
                now_s = time.time()
                # FIX: Always use current time for ticker updates to ensure chart continuity,
                # especially for low-volume assets like VIX.
                quote_ts = now_s

                # Dedup: only emit when price, delta OR volume has changed
                last_quote_key = f"{symbol}_{price}_{accumulated_delta:.4f}_{accumulated_vol:.4f}"
                prev_quote_key = self._last_quote_cache.get(symbol, "")
                
                # Pulse every 5 seconds or whenever data changes
                time_pulse = (now_s % 5.0 < 0.25) 
                should_emit = (last_quote_key != prev_quote_key) or time_pulse

                if should_emit:
                    self._last_quote_cache[symbol] = last_quote_key
                    event = MarketDataEvent(
                        symbol=symbol,
                        timestamp=quote_ts,
                        event_type="TICK",
                        last=price,
                        delta=accumulated_delta,
                        # FIX (BUG 6): send accumulated volume in tick, not None
                        volume=accumulated_vol,
                        source="MT5"
                    )
                    event.latency_ms = (time.time() - tick_start) * 1000
                    if self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED):
                        self._event_buffer.push(event)
                        self._symbol_buffer.update(event)
                        self._metrics.messages_received += 1
                        self._metrics.last_message_time  = time.time()
                        self._update_latency_metrics(event.latency_ms)

        # ── 3. Candle polling (once per second) ───────────────────────────────
        now_clk = time.time()
        if now_clk - self._last_candle_poll >= 1.0:
            self._last_candle_poll = now_clk
            try:
                df = connector.get_latest_candles(broker_symbol, timeframe="1m", n=5)
                if df is not None and not df.empty:
                    latest_row = df.iloc[-1]
                    try:
                        bar_ts = int(latest_row['time'].timestamp())
                    except (AttributeError, TypeError):
                        bar_ts = (
                            int(latest_row['time'])
                            if isinstance(latest_row['time'], (int, float))
                            else int(time.time())
                        )

                    # FIX (BUG 4,5): reset per-candle accumulators when bar changes
                    prev_bar_ts = self._mt5_bar_ts.get(s_upper, 0)
                    if bar_ts > prev_bar_ts:
                        self._mt5_bar_ts[s_upper]    = bar_ts
                        self._mt5_delta_acc[s_upper] = 0.0
                        self._mt5_vol_acc[s_upper]   = 0.0
                        accumulated_delta = 0.0
                        accumulated_vol   = 0.0

                    candle_event = MarketDataEvent(
                        symbol=symbol,
                        timestamp=bar_ts,
                        event_type="BAR",
                        open=float(latest_row.get('Open',  latest_row.get('open',  0))),
                        high=float(latest_row.get('High',  latest_row.get('high',  0))),
                        low=float(latest_row.get('Low',   latest_row.get('low',   0))),
                        close=float(latest_row.get('Close', latest_row.get('close', 0))),
                        volume=float(
                            latest_row.get('real_volume') or
                            latest_row.get('tick_volume') or
                            latest_row.get('Volume') or
                            accumulated_vol or 0
                        ),
                        # FIX (BUG 5): use full candle-accumulated delta, not just batch
                        delta=accumulated_delta,
                        source="MT5"
                    )
                    self._symbol_buffer.update(candle_event)
                    if self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED):
                        self._event_buffer.push(candle_event)

            except Exception as e:
                logger.debug(f"Error polling candle for {symbol}: {e}")

        # ── 4. Order book ─────────────────────────────────────────────────────
        if should_poll_book and hasattr(connector, 'get_book_snapshot'):
            self._poll_mt5_book(symbol, s_upper, broker_symbol, connector)

    def _poll_mt5_book(
        self,
        symbol: str,
        s_upper: str,
        broker_symbol: str,
        connector
    ) -> None:
        try:
            depth     = self._symbol_depths.get(s_upper, 50)
            book_data = connector.get_book_snapshot(broker_symbol, limit=depth)
            if not book_data:
                return

            bids_list = book_data.get("bids", [])
            asks_list = book_data.get("asks", [])

            with self._pb_lock:
                if s_upper not in self._persistent_books:
                    self._persistent_books[s_upper] = {
                        "bids": {}, "asks": {}, "last_update": 0
                    }
                pb = self._persistent_books[s_upper]
                for b in bids_list:
                    pb["bids"][float(b["price"])] = float(b["size"])
                for a in asks_list:
                    pb["asks"][float(a["price"])] = float(a["size"])
                if bids_list and asks_list:
                    mid   = (float(bids_list[0]["price"]) + float(asks_list[0]["price"])) / 2
                    p_min = mid * 0.5
                    p_max = mid * 1.5
                    pb["bids"] = {
                        p: v for p, v in pb["bids"].items() if p_min <= p and v > 0
                    }
                    pb["asks"] = {
                        p: v for p, v in pb["asks"].items() if p <= p_max and v > 0
                    }
                pb["last_update"] = time.time()
                pb_snap           = self._persistent_books.get(s_upper, {"bids": {}, "asks": {}})

            current_bid_sizes = {float(b["price"]): float(b["size"]) for b in bids_list}
            current_ask_sizes = {float(a["price"]): float(a["size"]) for a in asks_list}

            with self._pb_lock:
                merged_emit_bids = [
                    {"price": price_lvl, "size": current_bid_sizes.get(price_lvl, size_lvl), "count": 1}
                    for price_lvl, size_lvl in sorted(pb_snap["bids"].items(), reverse=True)
                    if current_bid_sizes.get(price_lvl, size_lvl) > 0
                ]
                merged_emit_asks = [
                    {"price": price_lvl, "size": current_ask_sizes.get(price_lvl, size_lvl), "count": 1}
                    for price_lvl, size_lvl in sorted(pb_snap["asks"].items())
                    if current_ask_sizes.get(price_lvl, size_lvl) > 0
                ]

            snapshot = OrderBookSnapshot(
                symbol=symbol,
                bids=[BookLevel(price=float(b["price"]), size=float(b["size"]), count=1) for b in bids_list],
                asks=[BookLevel(price=float(a["price"]), size=float(a["size"]), count=1) for a in asks_list]
            )
            # Calculate midpoint and spread
            midpoint = 0.0
            spread = 0.0
            if bids_list and asks_list:
                best_bid = float(bids_list[0]["price"])
                best_ask = float(asks_list[0]["price"])
                midpoint = (best_bid + best_ask) / 2
                spread = best_ask - best_bid

            book_event = MarketDataEvent(
                symbol=symbol,
                timestamp=pb["last_update"],
                event_type="BOOK",
                bids=merged_emit_bids[:200],
                asks=merged_emit_asks[:200],
                midpoint=midpoint,
                spread=spread,
                source="MT5"
            )
            if self._running:
                self._symbol_buffer.update_book(snapshot)
                if self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED):
                    self._event_buffer.push(book_event)

        except Exception as e:
            logger.debug(f"Error polling book for {symbol}: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # Crypto polling
    # ─────────────────────────────────────────────────────────────────────────

    def _poll_crypto_symbol(
        self,
        symbol: str,
        broker_symbol: str,
        should_poll_book: bool = True
    ) -> None:
        now     = time.time()
        s_upper = symbol.upper()

        # ── Multi-Broker Connector Selection ──
        connector = self._crypto_connector_cache.get(s_upper)
        if not connector:
            # Try master first
            master_conn = self._get_connector("crypto")
            all_conns = [master_conn] if master_conn else []
            
            # Get all other connectors
            from src.services.crypto_manager import get_crypto_manager
            from src.live.crypto_connector import get_connector
            manager = get_crypto_manager()
            for acc in manager.get_accounts():
                c = get_connector(acc["id"])
                if c and c not in all_conns:
                    all_conns.append(c)
            
            # Test which one works for this symbol
            for c in all_conns:
                try:
                    if not c.connected:
                        c.connect()
                    
                    test_sym = c._resolve_sym(symbol)
                    if test_sym:
                        # Success: Symbol resolved locally in this broker's markets
                        connector = c
                        broker_symbol = test_sym
                        self._crypto_connector_cache[s_upper] = c
                        logger.info(f"[MDE] Mapped {symbol} to broker {c.exchange_id} (Resolved: {test_sym})")
                        break
                except Exception as e:
                    logger.warning(f"[MDE] Error checking symbol {symbol} on {c.exchange_id if hasattr(c, 'exchange_id') else 'unknown'}: {e}")
                    continue
        
        if not connector:
            return

        try:
            # ── 1. Fetch and classify recent trades (Throttled to 1.0s) ──────
            if not hasattr(self, '_last_crypto_trade_poll'):
                self._last_crypto_trade_poll = {}
            
            last_trade_poll = self._last_crypto_trade_poll.get(s_upper, 0)
            if now - last_trade_poll >= 0.5:
                self._last_crypto_trade_poll[s_upper] = now
                trades = connector.get_trades(broker_symbol, limit=50)
            else:
                trades = None
            current_bar_ts = self._crypto_delta_bar_ts.get(s_upper, 0)
            if trades:
                seen         = self._crypto_seen_trade_ids.get(s_upper, set())
                new_buy      = 0.0
                new_sell     = 0.0
                latest_price = 0.0
                latest_ts    = now
                new_ids      = set()
                trade_batch  = []

                for t in trades:
                    tid = t.get('id', '')
                    if tid and tid in seen:
                        continue
                    if tid:
                        new_ids.add(tid)

                    t_amount = float(t['amount'])
                    t_price  = float(t['price'])
                    t_side   = str(t.get('side', 'BUY')).upper()
                    raw_ts   = float(t['timestamp'])
                    if raw_ts > 1e10:
                        raw_ts = raw_ts / 1000.0

                    trade_bar_ts = int(raw_ts // 60) * 60  # floor to 1-min boundary
                    
                    if current_bar_ts > 0 and trade_bar_ts > current_bar_ts:
                        # FAST BAR TRANSITION: Cross minute boundary directly via trades!
                        logger.info(f"[BAR] Fast trade transition for {s_upper} to {trade_bar_ts}")
                        
                        # Add any pending accumulators before zeroing
                        self._crypto_delta_acc[s_upper]  = self._crypto_delta_acc.get(s_upper, 0.0) + (new_buy - new_sell)
                        self._crypto_volume_acc[s_upper] = self._crypto_volume_acc.get(s_upper, 0.0) + (new_buy + new_sell)
                        new_buy = 0.0
                        new_sell = 0.0
                        
                        self._crypto_delta_acc[s_upper]   = 0.0
                        self._crypto_volume_acc[s_upper]  = 0.0
                        self._crypto_delta_bar_ts[s_upper] = trade_bar_ts
                        current_bar_ts = trade_bar_ts
                        
                        # Reset the live candle for the new bar using this trade
                        self._crypto_live_candle[s_upper] = {
                            'open': t_price, 'high': t_price,
                            'low': t_price, 'close': t_price
                        }
                        
                        if t_side == 'BUY':
                            new_buy += t_amount
                        else:
                            new_sell += t_amount
                    else:
                        if t_side == 'BUY':
                            new_buy  += t_amount
                        else:
                            new_sell += t_amount

                        # ── Update live candle from trade price ────────────────
                        lc = self._crypto_live_candle.get(s_upper)
                        if lc is None:
                            self._crypto_live_candle[s_upper] = {
                                'open': t_price, 'high': t_price,
                                'low': t_price, 'close': t_price
                            }
                        else:
                            lc['high']  = max(lc['high'], t_price)
                            lc['low']   = min(lc['low'],  t_price)
                            lc['close'] = t_price
                    
                    latest_price = t_price
                    latest_ts    = raw_ts

                    trade_ev = MarketDataEvent(
                        symbol=symbol,
                        timestamp=latest_ts,
                        event_type="TRADE",
                        last=t_price,
                        last_size=self._normalize_crypto_val(symbol, t_amount, t_price, broker_symbol),
                        side=t_side,
                        source="CRYPTO"
                    )
                    trade_batch.append(trade_ev)
                    self._trade_buffer.push(TradeEvent(
                        symbol=symbol, timestamp=latest_ts,
                        price=t_price, size=t_amount, side=t_side, trade_id=tid
                    ))

                if new_ids:
                    if trade_batch and self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED):
                        self._event_buffer.push_batch(trade_batch)

                    # FIX: Use a bounded set or preserve order properly to prevent re-processing old trades.
                    # Since sets are unordered, truncating list(set) removes random items.
                    if not isinstance(seen, dict):
                        # Convert legacy set to dict (which preserves insertion order)
                        seen = {k: True for k in seen}
                        self._crypto_seen_trade_ids[s_upper] = seen
                    
                    for nid in new_ids:
                        seen[nid] = True
                        
                    # Maintain max size of 5000
                    if len(seen) > 5000:
                        # Keep only the last 2000 items
                        keys_to_keep = list(seen.keys())[-2000:]
                        seen = {k: True for k in keys_to_keep}
                        
                    self._crypto_seen_trade_ids[s_upper] = seen

                    # Update accumulators
                    self._crypto_delta_acc[s_upper]  = (
                        self._crypto_delta_acc.get(s_upper, 0.0) + (new_buy - new_sell)
                    )
                    self._crypto_volume_acc[s_upper] = (
                        self._crypto_volume_acc.get(s_upper, 0.0) + (new_buy + new_sell)
                    )

                    # Use a representative price for normalization (latest_price)
                    # We normalize the ACCUMULATED values for total accuracy in labels
                    acc_v = self._crypto_volume_acc.get(s_upper, 0.0)
                    acc_d = self._crypto_delta_acc.get(s_upper, 0.0)
                    norm_vol   = self._normalize_crypto_val(symbol, acc_v, latest_price, broker_symbol)
                    norm_delta = self._normalize_crypto_val(symbol, acc_d, latest_price, broker_symbol)
                    norm_last_size = self._normalize_crypto_val(symbol, new_buy + new_sell, latest_price, broker_symbol)

                    side = "BUY" if acc_d >= 0 else "SELL"
                    bid_price = 0.0
                    ask_price = 0.0
                    with self._pb_lock:
                        pb = self._persistent_books.get(s_upper)
                        if pb and pb["bids"] and pb["asks"]:
                            bid_price = max(pb["bids"].keys())
                            ask_price = min(pb["asks"].keys())

                    # Use normalized values for emission
                    # IMPORTANT: Always include 'volume' and 'delta' (normalized totals for the bar)
                    # Also embed the live candle OHLC so the frontend can render the
                    # current candle shape without waiting for the next OHLCV poll.
                    lc = self._crypto_live_candle.get(s_upper, {})
                    event = MarketDataEvent(
                        symbol=symbol,
                        timestamp=latest_ts,
                        event_type="TICK",
                        last=latest_price,
                        bid=bid_price,
                        ask=ask_price,
                        open=lc.get('open', latest_price),
                        high=lc.get('high', latest_price),
                        low=lc.get('low', latest_price),
                        close=latest_price,
                        last_size=norm_last_size,
                        volume=norm_vol,
                        delta=norm_delta,
                        side=side,
                        source="CRYPTO"
                    )
                    if self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED):
                        self._event_buffer.push(event)
                        self._symbol_buffer.update(event)
                        self._metrics.messages_received += 1
                        self._metrics.last_message_time  = time.time()

            # ── 1b. Fast ticker poll (200ms) — fetch LIVE price between trade polls ──
            # This is the key to smooth price movement: get_tick() calls
            # exchange.fetch_ticker() which returns the real-time last price,
            # so the candle close updates 5x/sec instead of waiting 0.5s for trades.
            else:
                if not hasattr(self, '_last_crypto_ticker_poll'):
                    self._last_crypto_ticker_poll: Dict[str, float] = {}
                last_ticker_poll = self._last_crypto_ticker_poll.get(s_upper, 0)
                if now - last_ticker_poll >= 0.2:
                    self._last_crypto_ticker_poll[s_upper] = now
                    try:
                        ticker_data = connector.get_tick(broker_symbol)
                        
                        # Debug log: show what ticker returned
                        if not hasattr(self, '_ticker_debug_count'):
                            self._ticker_debug_count = {}
                        self._ticker_debug_count[s_upper] = self._ticker_debug_count.get(s_upper, 0) + 1
                        
                        if self._ticker_debug_count[s_upper] % 20 == 0:
                            logger.info(f"[TICKER_DEBUG] {s_upper}: {ticker_data}")
                        
                        if ticker_data and ticker_data.get('last') and ticker_data['last'] > 0:
                            live_price = float(ticker_data['last'])

                            # Check if local time crossed the minute boundary
                            tick_bar_ts = int(now // 60) * 60
                            current_bar_ts = self._crypto_delta_bar_ts.get(s_upper, 0)
                            
                            if current_bar_ts > 0 and tick_bar_ts > current_bar_ts:
                                logger.info(f"[BAR] Fast ticker transition for {s_upper} to {tick_bar_ts}")
                                self._crypto_delta_acc[s_upper]   = 0.0
                                self._crypto_volume_acc[s_upper]  = 0.0
                                self._crypto_delta_bar_ts[s_upper] = tick_bar_ts
                                self._crypto_live_candle[s_upper] = {
                                    'open': live_price, 'high': live_price,
                                    'low': live_price, 'close': live_price
                                }
                            else:
                                lc = self._crypto_live_candle.get(s_upper)
                                if lc is None:
                                    self._crypto_live_candle[s_upper] = {
                                        'open': live_price, 'high': live_price,
                                        'low': live_price, 'close': live_price
                                    }
                                else:
                                    lc['high']  = max(lc['high'], live_price)
                                    lc['low']   = min(lc['low'],  live_price)
                                    lc['close'] = live_price

                            acc_v = self._crypto_volume_acc.get(s_upper, 0.0)
                            acc_d = self._crypto_delta_acc.get(s_upper, 0.0)
                            norm_vol_c   = self._normalize_crypto_val(symbol, acc_v, live_price, broker_symbol)
                            norm_delta_c = self._normalize_crypto_val(symbol, acc_d, live_price, broker_symbol)
                            side_c = "BUY" if acc_d >= 0 else "SELL"

                            lc_data = self._crypto_live_candle.get(s_upper, {})
                            bid_p = float(ticker_data.get('bid') or 0)
                            ask_p = float(ticker_data.get('ask') or 0)
                            event = MarketDataEvent(
                                symbol=symbol,
                                timestamp=now,
                                event_type="TICK",
                                last=live_price,
                                bid=bid_p,
                                ask=ask_p,
                                open=lc_data.get('open', live_price),
                                high=lc_data.get('high', live_price),
                                low=lc_data.get('low', live_price),
                                close=live_price,
                                last_size=0,
                                volume=norm_vol_c,
                                delta=norm_delta_c,
                                side=side_c,
                                source="CRYPTO"
                            )
                            if self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED):
                                self._event_buffer.push(event)
                                self._symbol_buffer.update(event)
                                self._metrics.messages_received += 1
                                self._metrics.last_message_time  = time.time()
                                # Debug log every 20th tick to verify prices
                                if self._ticker_debug_count[s_upper] % 20 == 0:
                                    logger.info(f"[TICK_EMITTED] {symbol} price={live_price} bid={bid_p} ask={ask_p}")
                        else:
                            # Ticker returned 0 or empty - log occasionally
                            if self._ticker_debug_count[s_upper] % 50 == 0:
                                logger.warning(f"[TICKER_EMPTY] {s_upper}: last={ticker_data.get('last', 'N/A')}")
                    except Exception as e:
                        logger.warning(f"Fast ticker poll error for {symbol}: {e}")

            # ── 2. Candle polling (Throttled to 1.0s for real-time accuracy) ──────
            # FIX: Changed from 3.0s to 1.0s to reduce latency and prevent candle gaps
            last_candle_poll = self._last_crypto_candle_poll.get(s_upper, 0)
            if now - last_candle_poll >= 1.0:
                self._last_crypto_candle_poll[s_upper] = now
                try:
                    ohlcv = connector.get_ohlcv(broker_symbol, timeframe="1m", limit=100)
                    if ohlcv:
                        prev_live_ts = self._crypto_delta_bar_ts.get(s_upper, 0)
                        last_emitted = self._crypto_last_emitted_ohlcv_ts.get(s_upper, 0)
                        
                        # 1. Emit any missed or just-closed bars from OHLCV history
                        for i in range(len(ohlcv) - 1):
                            bar = ohlcv[i]
                            bar_ts = int(float(bar[0]) / 1000.0)
                            
                            if bar_ts > last_emitted:
                                bar_close = float(bar[4])
                                # Global normalization for volume
                                bar_vol = self._normalize_crypto_val(symbol, float(bar[5]), bar_close, broker_symbol)
                                
                                ev = MarketDataEvent(
                                    symbol=symbol, timestamp=bar_ts, event_type="OHLCV",
                                    open=float(bar[1]), high=float(bar[2]), low=float(bar[3]),
                                    close=bar_close, volume=bar_vol, delta=0.0, source="CRYPTO"
                                )
                                self._event_buffer.push(ev)
                                self._symbol_buffer.update(ev)
                                self._crypto_last_emitted_ohlcv_ts[s_upper] = bar_ts
                                logger.debug(f"[OHLCV] Emitted closed bar for {s_upper} at {bar_ts}")

                        # 2. Check for transition
                        latest_bar = ohlcv[-1]
                        latest_ts  = int(float(latest_bar[0]) / 1000.0)
                        latest_close = float(latest_bar[4])
                        current_bar_ts = self._crypto_delta_bar_ts.get(s_upper, 0)
                        
                        if latest_ts > prev_live_ts:
                            logger.info(f"[BAR] {s_upper} advanced to new forming bar at {latest_ts}")
                            self._crypto_delta_acc[s_upper]   = 0.0
                            self._crypto_volume_acc[s_upper]  = 0.0
                            self._crypto_delta_bar_ts[s_upper] = latest_ts
                            # Reset live candle for new bar using exchange's opening price
                            self._crypto_live_candle[s_upper] = {
                                'open': float(latest_bar[1]),
                                'high': float(latest_bar[2]),
                                'low':  float(latest_bar[3]),
                                'close': latest_close
                            }

                        # FIX: Sync live candle with exchange OHLCV BUT preserve live formation
                        # Only update high/low from exchange if they extend beyond current live values
                        # NEVER overwrite the close during formation - the live candle close is the real-time price
                        lc = self._crypto_live_candle.get(s_upper)
                        if lc:
                            # Only update high/low if exchange values extend beyond our live tracking
                            exchange_high = float(latest_bar[2])
                            exchange_low = float(latest_bar[3])
                            lc['high'] = max(lc['high'], exchange_high)
                            lc['low'] = min(lc['low'], exchange_low)
                            # KEEP the live close - don't overwrite with potentially stale exchange value
                            # The live close is continuously updated by ticker/trades polling
                        else:
                            self._crypto_live_candle[s_upper] = {
                                'open': float(latest_bar[1]),
                                'high': float(latest_bar[2]),
                                'low':  float(latest_bar[3]),
                                'close': latest_close
                            }

                        raw_ex_vol = float(latest_bar[5]) # Assuming this is the raw exchange volume from the OHLCV bar
                        norm_ex_vol = self._normalize_crypto_val(symbol, raw_ex_vol, latest_close, broker_symbol)
                        
                        # Live acc normalized
                        norm_local_vol = self._normalize_crypto_val(symbol, self._crypto_volume_acc.get(s_upper, 0.0), latest_close, broker_symbol)
                        norm_local_delta = self._normalize_crypto_val(symbol, self._crypto_delta_acc.get(s_upper, 0.0), latest_close, broker_symbol)

                        # CRITICAL FIX: Use LIVE candle values (from ticker/trades) for close, NOT the exchange's stale close
                        # The live candle lc has the real-time close price that was updated by the fast ticker poll
                        live_close = lc.get('close', latest_close) if lc else latest_close
                        
                        live_ev = MarketDataEvent(
                            symbol=symbol, timestamp=latest_ts, event_type="OHLCV",
                            open=float(latest_bar[1]), high=float(latest_bar[2]),
                            low=float(latest_bar[3]), close=live_close,
                            volume=max(norm_ex_vol, norm_local_vol),
                            delta=norm_local_delta,
                            source="CRYPTO"
                        )
                        self._symbol_buffer.update(live_ev)
                        if self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED):
                            self._event_buffer.push(live_ev)

                except Exception as e:
                    logger.error(f"Error polling OHLCV for {symbol}: {e}")

            # ── 3. Order book ──────────────────────────────────────────────────
            if should_poll_book:
                self._poll_crypto_book(symbol, s_upper, broker_symbol, connector, now)

        except Exception as e:
            logger.error(f"Error in crypto poll for {symbol}: {e}")
            self._metrics.errors_count += 1

    def _normalize_crypto_val(self, symbol: str, val: float, price: float, broker: str = "") -> float:
        """
        Calculates the normalized volume (always in Base Units like BTC / ETH).
        FIX: Improved heuristics to correctly detect if value is in base units or quote units.
        """
        # Guard against invalid inputs
        if val is None or val == 0 or price is None or price <= 0:
            return val or 0.0
        
        abs_v = abs(val)
        broker_l = (broker or "").lower()
        s_up = symbol.upper()
        
        # 1. Blofin/OKX Multiplier Map (Contract sizes for USDT pairs)
        if 'blofin' in broker_l or 'okx' in broker_l:
            mult = 1.0
            if 'BTC' in s_up: mult = 0.001
            elif 'ETH' in s_up: mult = 0.01
            elif 'SOL' in s_up: mult = 0.1
            elif 'LTC' in s_up: mult = 0.1
            elif 'XRP' in s_up: mult = 10.0
            elif 'ADA' in s_up: mult = 10.0
            
            # Heuristic: If value is a whole number >= 1 and looks like contracts
            if abs_v >= 1.0 and abs_v == int(abs_v):
                # Check if raw value would be insane as base units (> $500k notional per trade)
                if (abs_v * price) > 500_000:
                    return val * mult
                    
        # 2. General Dynamic Heuristic (Notional Cap)
        # If notional > $1.5M in one tick/forming bar, it's definitely NOT base units.
        # However, for high-priced assets (e.g., BTC at $100k), even reasonable base unit volumes
        # can have large notionals. So we check BOTH notional AND magnitude.
        notional = abs_v * price
        
        # If notional > $1.5M AND the value is a reasonable-looking quote amount (whole numbers)
        if notional > 1_500_000 and abs_v == int(abs_v):
            # Assume it was reported in USDT/USD (quote currency)
            return val / price
        
        # If value is extremely large (likely in USDT) and dividing gives a reasonable base amount
        if notional > 1_500_000:
            potential_base = val / price
            # If dividing gives us a very small number (< 0.01 BTC etc), it's likely already in base
            if potential_base < 0.001:
                return val  # Keep as-is, it's probably already base units
            return potential_base
            
        return val

    def _poll_crypto_book(
        self,
        symbol: str,
        s_upper: str,
        broker_symbol: str,
        connector,
        now: float
    ) -> None:
        """Rate-limited order book polling for crypto (Binance-aware limits)."""
        depth = self._symbol_depths.get(s_upper, 50)

        # Map requested depth to nearest valid Binance limit
        valid_limits   = [5, 10, 20, 50, 100, 500, 1000]
        binance_limit  = next((lim for lim in valid_limits if depth <= lim), 1000)

        # Throttle more aggressively for deeper books
        if   binance_limit <= 100:  req_delay = 0.5
        elif binance_limit <= 500:  req_delay = 1.0
        elif binance_limit <= 1000: req_delay = 1.5
        else:                       req_delay = 3.0

        if not hasattr(self, '_last_crypto_book_poll_strict'):
            self._last_crypto_book_poll_strict = {}

        last_strict_poll = self._last_crypto_book_poll_strict.get(s_upper, 0)
        if now - last_strict_poll < req_delay:
            return

        self._last_crypto_book_poll_strict[s_upper] = now
        try:
            book = connector.get_book_snapshot(broker_symbol, limit=binance_limit)
            if not book or not book.get("bids") or not book.get("asks"):
                return

            bids_raw = book.get("bids", [])
            asks_raw = book.get("asks", [])

            with self._pb_lock:
                if s_upper not in self._persistent_books:
                    self._persistent_books[s_upper] = {
                        "bids": {}, "asks": {}, "last_update": 0
                    }
                pb = self._persistent_books[s_upper]
                for b in bids_raw:
                    pb["bids"][float(b["price"])] = float(b["size"])
                for a in asks_raw:
                    pb["asks"][float(a["price"])] = float(a["size"])
                if bids_raw and asks_raw:
                    try:
                        mid   = (float(bids_raw[0]["price"]) + float(asks_raw[0]["price"])) / 2
                        p_min = mid * 0.7
                        p_max = mid * 1.3
                        pb["bids"] = {
                            p: v for p, v in pb["bids"].items() if p_min <= p and v > 0
                        }
                        pb["asks"] = {
                            p: v for p, v in pb["asks"].items() if p <= p_max and v > 0
                        }
                    except (IndexError, KeyError, TypeError):
                        pass
                pb["last_update"] = time.time()

            bids = [{"price": b["price"], "size": b["size"], "count": 1} for b in bids_raw]
            asks = [{"price": a["price"], "size": a["size"], "count": 1} for a in asks_raw]

            # Calculate midpoint and spread
            midpoint = 0.0
            spread = 0.0
            if bids_raw and asks_raw:
                best_bid = float(bids_raw[0]["price"])
                best_ask = float(asks_raw[0]["price"])
                midpoint = (best_bid + best_ask) / 2
                spread = best_ask - best_bid

            book_event = MarketDataEvent(
                symbol=symbol,
                timestamp=book.get("timestamp", now),
                event_type="BOOK_UPDATE",
                bids=bids,
                asks=asks,
                midpoint=midpoint,
                spread=spread,
                source="CRYPTO"
            )
            snapshot = OrderBookSnapshot(
                symbol=symbol,
                bids=[BookLevel(price=b["price"], size=b["size"], count=1) for b in bids],
                asks=[BookLevel(price=a["price"], size=a["size"], count=1) for a in asks]
            )
            self._symbol_buffer.update_book(snapshot)
            if self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED):
                self._event_buffer.push(book_event)

        except Exception as e:
            logger.debug(f"Error polling crypto book for {symbol}: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # Platform detection
    # ─────────────────────────────────────────────────────────────────────────

    def _detect_platform(self, symbol: str) -> str:
        s = symbol.upper()
        if any(x in s for x in ["USDT", "USDC", "BTC", "ETH", "SOL", "/USDT", ":USDT"]):
            return "crypto"
        if self._platform == "tradovate":
            return "tradovate"
        return "mt5"

    # ─────────────────────────────────────────────────────────────────────────
    # Reconnect
    # ─────────────────────────────────────────────────────────────────────────

    def _try_reconnect(self) -> bool:
        logger.info(f"Intentando reconectar plataforma: {self._platform}")
        self._metrics.reconnect_count += 1
        any_success = False
        with self._connector_lock:
            if self._platform not in self._connectors:
                try:
                    self._get_connector(self._platform)
                except Exception as e:
                    logger.error(f"Error initializing connector for {self._platform}: {e}")
                    return False
            connector = self._connectors.get(self._platform)
            if not connector:
                return False
            try:
                if self._platform == "mt5":
                    connect_kwargs = {}
                    if hasattr(self, '_mt5_connect_path') and self._mt5_connect_path:
                        connect_kwargs['path'] = self._mt5_connect_path
                    if connector.connect(**connect_kwargs):
                        logger.info(f"Reconexión exitosa para {self._platform}")
                        any_success = True
                    else:
                        logger.warning(f"Reconexión fallida para {self._platform}")
                else:
                    # CRITICAL FIX: For crypto (and other non-MT5), verify connector and set ONLINE status
                    logger.info(f"Conector {self._platform} verificado correctamente")
                    any_success = True
                    # Set status to ONLINE for crypto - this was missing!
                    self._update_status(FeedStatus.ONLINE)
                    self._metrics.connected_since = time.time()
                    logger.info(f"[CRYPTO] Engine status set to ONLINE for {self._platform}")
            except Exception as e:
                logger.error(f"Error reconectando {self._platform}: {e}")
        return any_success

    # ─────────────────────────────────────────────────────────────────────────
    # Status / metrics helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _update_status(self, new_status: FeedStatus) -> None:
        old_status    = self._status
        self._status  = new_status
        self._metrics.status = new_status
        if old_status != new_status:
            logger.info(f"Estado del feed: {old_status.value} -> {new_status.value}")
            for callback in self._status_callbacks:
                try:
                    callback(new_status)
                except Exception as e:
                    logger.error(f"Error en callback de estado: {e}")

    def _update_latency_metrics(self, latency_ms: float) -> None:
        self._metrics.max_latency_ms = max(self._metrics.max_latency_ms, latency_ms)
        self._metrics.min_latency_ms = min(self._metrics.min_latency_ms, latency_ms)
        alpha = 0.1
        self._metrics.avg_latency_ms = (
            alpha * latency_ms + (1 - alpha) * self._metrics.avg_latency_ms
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def status(self) -> FeedStatus:
        return self._status

    @property
    def is_online(self) -> bool:
        return self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED)

    @property
    def platform(self) -> str:
        return self._platform

    @property
    def metrics(self) -> FeedMetrics:
        return self._metrics

    def get_status(self) -> Dict[str, Any]:
        return {
            "status":            self._status.value,
            "is_running":        self._running,
            "metrics":           self._metrics.to_dict(),
            "buffer_metrics":    self._event_buffer.get_metrics(),
            "subscribed_symbols": list(self._symbols)
        }

    def get_latest_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        event = self._symbol_buffer.get_latest(symbol)
        return event.to_dict() if event else None

    def get_book_snapshot(self, symbol: str, limit: int = 100) -> Optional[Dict[str, Any]]:
        symbol = symbol.upper()
        with self._pb_lock:
            if symbol in self._persistent_books:
                pb          = self._persistent_books[symbol]
                sorted_bids = sorted(pb["bids"].items(), key=lambda x: x[0], reverse=True)
                sorted_asks = sorted(pb["asks"].items(), key=lambda x: x[0])
                mid = 0
                if sorted_bids and sorted_asks:
                    mid = (sorted_bids[0][0] + sorted_asks[0][0]) / 2
                safe_limit = min(50000, max(20, limit))
                return {
                    "symbol":    symbol,
                    "timestamp": pb.get("last_update", time.time()),
                    "midpoint":  mid,
                    "bids": [
                        {"price": p, "size": v, "count": 1}
                        for p, v in sorted_bids[:safe_limit]
                    ],
                    "asks": [
                        {"price": p, "size": v, "count": 1}
                        for p, v in sorted_asks[:safe_limit]
                    ]
                }
        book = self._symbol_buffer.get_book(symbol)
        return book.to_dict() if book else None

    def get_recent_trades(self, symbol: str, n: int = 100) -> List[Dict[str, Any]]:
        trades = self._trade_buffer.get_by_symbol(symbol, n)
        return [t.to_dict() for t in trades]

    def get_candles(self, symbol: str, n: int = 100) -> List[Dict[str, Any]]:
        events = self._symbol_buffer.get_history(symbol, n)
        return [e.to_dict() for e in events if e.event_type in ("OHLCV", "BAR")]

    def request_depth(self, symbol: str, levels: int) -> None:
        symbol      = symbol.upper()
        safe_levels = min(50000, max(20, levels))
        current     = self._symbol_depths.get(symbol, 0)
        if safe_levels != current:
            self._symbol_depths[symbol] = safe_levels
            logger.info(f"Depth request for {symbol} updated to {safe_levels} levels")

    def subscribe_to_events(self, callback: Callable[[MarketDataEvent], None]) -> None:
        self._event_buffer.subscribe(callback)

    def unsubscribe_from_events(self, callback: Callable[[MarketDataEvent], None]) -> None:
        self._event_buffer.unsubscribe(callback)

    def subscribe_to_status(self, callback: Callable[[FeedStatus], None]) -> None:
        if callback not in self._status_callbacks:
            self._status_callbacks.append(callback)

    def unsubscribe_from_status(self, callback: Callable[[FeedStatus], None]) -> None:
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)


def get_market_data_engine() -> MarketDataEngine:
    return MarketDataEngine()