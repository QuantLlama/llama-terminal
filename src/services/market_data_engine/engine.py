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
        """
        original = symbol
        symbol = symbol.upper().strip()
        
        is_crypto = self._is_crypto_symbol(symbol)
        
        if is_crypto:
            if ':' in symbol:
                base = symbol.split(':')[0]
                symbol = base
            
            if '/USDT' in symbol and ':' not in symbol:
                symbol = f"{symbol}:USDT"
            elif '/USDC' in symbol and ':' not in symbol:
                symbol = f"{symbol}:USDC"
            elif '/USD' in symbol and ':' not in symbol:
                symbol = f"{symbol}:USD"
            
            clean = symbol.replace('/', '').replace(':', '')
            if clean.endswith('USDT') and '/' not in symbol and ':' not in symbol:
                base = clean[:-4]
                symbol = f"{base}/USDT:USDT"
            elif clean.endswith('USDC') and '/' not in symbol and ':' not in symbol:
                base = clean[:-4]
                symbol = f"{base}/USDC:USDC"
        else:
            if '/USDT' in symbol and symbol.endswith(':USDT'):
                symbol = symbol.replace(':USDT', '')
            elif '/USDC' in symbol and symbol.endswith(':USDC'):
                symbol = symbol.replace(':USDC', '')
            
            parts = symbol.split('/')
            if len(parts) >= 3:
                symbol = f"{parts[0]}/{parts[1]}"
        
        return symbol

    def subscribe(self, symbols: List[str]) -> None:
        with self._symbols_lock:
            for symbol in symbols:
                original = symbol
                symbol = self._normalize_symbol_for_subscription(symbol)
                
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
        poll_start = time.time()
        now        = poll_start
        s_upper    = symbol.upper()
        
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
            error_count = self._symbol_error_count.get(s_upper, 0)
            last_success = self._symbol_last_success.get(s_upper, 0)
            
            if error_count >= 10:
                if now - last_success > 60:
                    logger.warning(f"[MDE_SKIP] Symbol {symbol} skipped (too many errors), will retry in 60s")
                    self._symbol_error_count[s_upper] = 0
                return
            
            if target_platform == "crypto":
                broker_symbol = symbol
            else:
                broker_symbol = resolve_symbol(symbol)
            
            if target_platform == "crypto":
                self._poll_crypto_symbol(symbol, broker_symbol, should_poll_book)
                self._symbol_error_count[s_upper] = 0
                self._symbol_last_success[s_upper] = now
                return

            connector = self._get_connector(target_platform)
            if not connector:
                self._symbol_error_count[s_upper] = self._symbol_error_count.get(s_upper, 0) + 1
                return

            self._poll_mt5_symbol(
                symbol, s_upper, broker_symbol, connector, should_poll_book
            )
            self._symbol_error_count[s_upper] = 0
            self._symbol_last_success[s_upper] = now

        except Exception as e:
            logger.error(f"Error polling símbolo {symbol}: {e}")
            self._metrics.errors_count += 1
            self._symbol_error_count[s_upper] = self._symbol_error_count.get(s_upper, 0) + 1
        finally:
            total_poll_time = (time.time() - poll_start) * 1000
            if total_poll_time > 250:
                logger.warning(f"HIGH_POLL_LATENCY: {symbol} took {total_poll_time:.1f}ms")

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
                is_future = any(x in s_upper for x in ["MES", "MNQ", "ES", "NQ", "CL", "GC", "RTY", "YM", "FDAX", "FESX"])
                use_real = 'volume_real' in ticks_df.columns
                v_col    = 'volume_real' if use_real and (is_future or ticks_df['volume_real'].sum() > 0) else 'volume'
                ts_col      = 'time_msc' if 'time_msc' in ticks_df.columns else 'time'
                max_tick_ts = float(ticks_df[ts_col].max())

                if max_tick_ts > last_processed_ts:
                    self._last_tick_time[s_upper] = max_tick_ts

                trade_batch   = []
                ticks_list    = ticks_df.to_dict('records')
                batch_buy_vol = 0.0
                batch_sell_vol = 0.0

                for tick in ticks_list:
                    t_ts = float(tick.get(ts_col, 0))
                    if t_ts <= last_processed_ts: continue

                    raw_v  = float(tick.get('volume_real') or tick.get('volume') or 0)
                    prev_v = self._last_abs_volume.get(s_upper, 0)
                    flags  = tick.get('flags', 0)

                    if flags & 32:
                        batch_buy_vol  += raw_v
                    elif flags & 64:
                        batch_sell_vol += raw_v

                    if prev_v == 0:
                        self._last_abs_volume[s_upper] = raw_v
                        if raw_v > 10: continue
                        t_vol = raw_v
                    else:
                        if raw_v >= prev_v:
                            delta_v = raw_v - prev_v
                            is_cumulative_feed = (raw_v > 100) or (prev_v > 100)
                            t_vol = 0 if (is_cumulative_feed and delta_v > 50000) else delta_v
                        else:
                            t_vol = raw_v if raw_v > 0 else 0
                        self._last_abs_volume[s_upper] = raw_v

                    t_side = ""
                    if flags & 32:
                        t_side = "BUY"
                    elif flags & 64:
                        t_side = "SELL"
                    elif t_vol > 0 and not (flags & 6):
                        t_side = "BUY" if tick['last'] >= tick['ask'] else "SELL"

                    if t_vol > 0 and t_side:
                        ts_val = float(tick['time_msc'] / 1000) if 'time_msc' in tick else float(tick['time'])
                        p = float(tick['last'])
                        trade_ev = MarketDataEvent(
                            symbol=symbol, timestamp=ts_val, event_type="TRADE",
                            last=p, last_size=t_vol, side=t_side, source="MT5"
                        )
                        trade_batch.append(trade_ev)
                        self._trade_buffer.push(TradeEvent(
                            symbol=symbol, timestamp=ts_val,
                            price=p, size=t_vol, side=t_side
                        ))

                if trade_batch:
                    self._event_buffer.push_batch(trade_batch)

                accumulated_delta += (batch_buy_vol - batch_sell_vol)
                accumulated_vol   += (batch_buy_vol + batch_sell_vol)
                self._mt5_delta_acc[s_upper] = accumulated_delta
                self._mt5_vol_acc[s_upper]   = accumulated_vol

        except Exception as e:
            logger.debug(f"Error processing ticks for {symbol}: {e}")

        if hasattr(connector, 'get_current_price'):
            price = connector.get_current_price(broker_symbol)
            if price:
                now_s = time.time()
                quote_ts = now_s
                last_quote_key = f"{symbol}_{price}_{accumulated_delta:.4f}_{accumulated_vol:.4f}"
                prev_quote_key = self._last_quote_cache.get(symbol, "")
                time_pulse = (now_s % 5.0 < 0.25) 
                should_emit = (last_quote_key != prev_quote_key) or time_pulse

                if should_emit:
                    self._last_quote_cache[symbol] = last_quote_key
                    event = MarketDataEvent(
                        symbol=symbol, timestamp=quote_ts, event_type="TICK",
                        last=price, delta=accumulated_delta, volume=accumulated_vol,
                        source="MT5"
                    )
                    event.latency_ms = (time.time() - tick_start) * 1000
                    if self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED):
                        self._event_buffer.push(event)
                        self._symbol_buffer.update(event)
                        self._metrics.messages_received += 1
                        self._metrics.last_message_time  = time.time()
                        self._update_latency_metrics(event.latency_ms)

        now_clk = time.time()
        if now_clk - self._last_candle_poll >= 1.0:
            self._last_candle_poll = now_clk
            try:
                df = connector.get_latest_candles(broker_symbol, timeframe="1m", n=5)
                if df is not None and not df.empty:
                    latest_row = df.iloc[-1]
                    bar_ts = int(latest_row['time'].timestamp()) if hasattr(latest_row['time'], 'timestamp') else int(latest_row['time'])
                    prev_bar_ts = self._mt5_bar_ts.get(s_upper, 0)
                    if bar_ts > prev_bar_ts:
                        self._mt5_bar_ts[s_upper]    = bar_ts
                        self._mt5_delta_acc[s_upper] = 0.0
                        self._mt5_vol_acc[s_upper]   = 0.0
                        accumulated_delta = 0.0
                        accumulated_vol   = 0.0

                    candle_event = MarketDataEvent(
                        symbol=symbol, timestamp=bar_ts, event_type="BAR",
                        open=float(latest_row.get('Open', latest_row.get('open', 0))),
                        high=float(latest_row.get('High', latest_row.get('high', 0))),
                        low=float(latest_row.get('Low', latest_row.get('low', 0))),
                        close=float(latest_row.get('Close', latest_row.get('close', 0))),
                        volume=float(latest_row.get('real_volume') or latest_row.get('tick_volume') or latest_row.get('Volume') or accumulated_vol or 0),
                        delta=accumulated_delta, source="MT5"
                    )
                    self._symbol_buffer.update(candle_event)
                    if self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED):
                        self._event_buffer.push(candle_event)
            except Exception as e:
                logger.debug(f"Error polling candle for {symbol}: {e}")

        if should_poll_book and hasattr(connector, 'get_book_snapshot'):
            self._poll_mt5_book(symbol, s_upper, broker_symbol, connector)

    def _poll_mt5_book(self, symbol: str, s_upper: str, broker_symbol: str, connector) -> None:
        try:
            depth     = self._symbol_depths.get(s_upper, 50)
            book_data = connector.get_book_snapshot(broker_symbol, limit=depth)
            if not book_data: return
            bids_list = book_data.get("bids", [])
            asks_list = book_data.get("asks", [])
            with self._pb_lock:
                if s_upper not in self._persistent_books:
                    self._persistent_books[s_upper] = {"bids": {}, "asks": {}, "last_update": 0}
                pb = self._persistent_books[s_upper]
                for b in bids_list: pb["bids"][float(b["price"])] = float(b["size"])
                for a in asks_list: pb["asks"][float(a["price"])] = float(a["size"])
                if bids_list and asks_list:
                    mid = (float(bids_list[0]["price"]) + float(asks_list[0]["price"])) / 2
                    p_min, p_max = mid * 0.5, mid * 1.5
                    pb["bids"] = {p: v for p, v in pb["bids"].items() if p_min <= p and v > 0}
                    pb["asks"] = {p: v for p, v in pb["asks"].items() if p <= p_max and v > 0}
                pb["last_update"] = time.time()
                pb_snap = self._persistent_books.get(s_upper, {"bids": {}, "asks": {}})
            current_bid_sizes = {float(b["price"]): float(b["size"]) for b in bids_list}
            current_ask_sizes = {float(a["price"]): float(a["size"]) for a in asks_list}
            with self._pb_lock:
                merged_emit_bids = [{"price": p, "size": current_bid_sizes.get(p, v), "count": 1} for p, v in sorted(pb_snap["bids"].items(), reverse=True) if current_bid_sizes.get(p, v) > 0]
                merged_emit_asks = [{"price": p, "size": current_ask_sizes.get(p, v), "count": 1} for p, v in sorted(pb_snap["asks"].items()) if current_ask_sizes.get(p, v) > 0]
            snapshot = OrderBookSnapshot(
                symbol=symbol,
                bids=[BookLevel(price=float(b["price"]), size=float(b["size"]), count=1) for b in bids_list],
                asks=[BookLevel(price=float(a["price"]), size=float(a["size"]), count=1) for a in asks_list]
            )
            midpoint, spread = 0.0, 0.0
            if bids_list and asks_list:
                midpoint = (float(bids_list[0]["price"]) + float(asks_list[0]["price"])) / 2
                spread = float(asks_list[0]["price"]) - float(bids_list[0]["price"])
            book_event = MarketDataEvent(
                symbol=symbol, timestamp=pb["last_update"], event_type="BOOK",
                bids=merged_emit_bids[:200], asks=merged_emit_asks[:200],
                midpoint=midpoint, spread=spread, source="MT5"
            )
            if self._running:
                self._symbol_buffer.update_book(snapshot)
                if self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED):
                    self._event_buffer.push(book_event)
        except Exception as e:
            logger.debug(f"Error polling book for {symbol}: {e}")

    def _poll_crypto_symbol(self, symbol: str, broker_symbol: str, should_poll_book: bool = True) -> None:
        now, s_upper = time.time(), symbol.upper()
        connector = self._crypto_connector_cache.get(s_upper)
        if not connector:
            master_conn = self._get_connector("crypto")
            all_conns = [master_conn] if master_conn else []
            from src.services.crypto_manager import get_crypto_manager
            from src.live.crypto_connector import get_connector
            manager = get_crypto_manager()
            for acc in manager.get_accounts():
                c = get_connector(acc["id"])
                if c and c not in all_conns: all_conns.append(c)
            for c in all_conns:
                try:
                    if not c.connected: c.connect()
                    test_sym = c._resolve_sym(symbol)
                    if test_sym: connector, broker_symbol = c, test_sym; self._crypto_connector_cache[s_upper] = c; break
                except: continue
        if not connector: return
        try:
            last_trade_poll = self._last_crypto_trade_poll.get(s_upper, 0)
            if now - last_trade_poll >= 0.5:
                self._last_crypto_trade_poll[s_upper] = now
                trades = connector.get_trades(broker_symbol, limit=50)
            else: trades = None
            current_bar_ts = self._crypto_delta_bar_ts.get(s_upper, 0)
            if trades:
                seen = self._crypto_seen_trade_ids.get(s_upper, set())
                new_buy, new_sell, latest_price, latest_ts, new_ids, trade_batch = 0.0, 0.0, 0.0, now, set(), []
                for t in trades:
                    tid = t.get('id', '')
                    if tid and tid in seen: continue
                    if tid: new_ids.add(tid)
                    t_amount, t_price, t_side, raw_ts = float(t['amount']), float(t['price']), str(t.get('side', 'BUY')).upper(), float(t['timestamp'])
                    if raw_ts > 1e10: raw_ts /= 1000.0
                    trade_bar_ts = int(raw_ts // 60) * 60
                    if current_bar_ts > 0 and trade_bar_ts > current_bar_ts:
                        self._crypto_delta_acc[s_upper] = self._crypto_delta_acc.get(s_upper, 0.0) + (new_buy - new_sell)
                        self._crypto_volume_acc[s_upper] = self._crypto_volume_acc.get(s_upper, 0.0) + (new_buy + new_sell)
                        new_buy, new_sell, self._crypto_delta_acc[s_upper], self._crypto_volume_acc[s_upper], self._crypto_delta_bar_ts[s_upper] = 0.0, 0.0, 0.0, 0.0, trade_bar_ts
                        current_bar_ts = trade_bar_ts
                        self._crypto_live_candle[s_upper] = {'open': t_price, 'high': t_price, 'low': t_price, 'close': t_price}
                        if t_side == 'BUY': new_buy += t_amount
                        else: new_sell += t_amount
                    else:
                        if t_side == 'BUY': new_buy += t_amount
                        else: new_sell += t_amount
                        lc = self._crypto_live_candle.get(s_upper)
                        if lc is None: self._crypto_live_candle[s_upper] = {'open': t_price, 'high': t_price, 'low': t_price, 'close': t_price}
                        else: lc['high'], lc['low'], lc['close'] = max(lc['high'], t_price), min(lc['low'], t_price), t_price
                    latest_price, latest_ts = t_price, raw_ts
                    trade_ev = MarketDataEvent(symbol=symbol, timestamp=latest_ts, event_type="TRADE", last=t_price, last_size=self._normalize_crypto_val(symbol, t_amount, t_price, broker_symbol), side=t_side, source="CRYPTO")
                    trade_batch.append(trade_ev)
                    self._trade_buffer.push(TradeEvent(symbol=symbol, timestamp=latest_ts, price=t_price, size=t_amount, side=t_side, trade_id=tid))
                if new_ids:
                    if trade_batch and self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED): self._event_buffer.push_batch(trade_batch)
                    if not isinstance(seen, dict): seen = {k: True for k in seen}; self._crypto_seen_trade_ids[s_upper] = seen
                    for nid in new_ids: seen[nid] = True
                    if len(seen) > 5000: seen = {k: True for k in list(seen.keys())[-2000:]}
                    self._crypto_seen_trade_ids[s_upper] = seen
                    self._crypto_delta_acc[s_upper] = self._crypto_delta_acc.get(s_upper, 0.0) + (new_buy - new_sell)
                    self._crypto_volume_acc[s_upper] = self._crypto_volume_acc.get(s_upper, 0.0) + (new_buy + new_sell)
                    acc_v, acc_d = self._crypto_volume_acc.get(s_upper, 0.0), self._crypto_delta_acc.get(s_upper, 0.0)
                    norm_vol, norm_delta, norm_last_size = self._normalize_crypto_val(symbol, acc_v, latest_price, broker_symbol), self._normalize_crypto_val(symbol, acc_d, latest_price, broker_symbol), self._normalize_crypto_val(symbol, new_buy + new_sell, latest_price, broker_symbol)
                    bid_price, ask_price = 0.0, 0.0
                    with self._pb_lock:
                        pb = self._persistent_books.get(s_upper)
                        if pb and pb["bids"] and pb["asks"]: bid_price, ask_price = max(pb["bids"].keys()), min(pb["asks"].keys())
                    lc = self._crypto_live_candle.get(s_upper, {})
                    event = MarketDataEvent(symbol=symbol, timestamp=latest_ts, event_type="TICK", last=latest_price, bid=bid_price, ask=ask_price, open=lc.get('open', latest_price), high=lc.get('high', latest_price), low=lc.get('low', latest_price), close=latest_price, last_size=norm_last_size, volume=norm_vol, delta=norm_delta, side="BUY" if acc_d >= 0 else "SELL", source="CRYPTO")
                    if self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED): self._event_buffer.push(event); self._symbol_buffer.update(event); self._metrics.messages_received += 1; self._metrics.last_message_time = time.time()
            else:
                last_ticker_poll = self._last_crypto_ticker_poll.get(s_upper, 0)
                if now - last_ticker_poll >= 0.2:
                    self._last_crypto_ticker_poll[s_upper] = now
                    try:
                        ticker_data = connector.get_tick(broker_symbol)
                        if ticker_data and ticker_data.get('last') and ticker_data['last'] > 0:
                            live_price = float(ticker_data['last'])
                            tick_bar_ts = int(now // 60) * 60
                            current_bar_ts = self._crypto_delta_bar_ts.get(s_upper, 0)
                            if current_bar_ts > 0 and tick_bar_ts > current_bar_ts:
                                self._crypto_delta_acc[s_upper], self._crypto_volume_acc[s_upper], self._crypto_delta_bar_ts[s_upper], self._crypto_live_candle[s_upper] = 0.0, 0.0, tick_bar_ts, {'open': live_price, 'high': live_price, 'low': live_price, 'close': live_price}
                            else:
                                lc = self._crypto_live_candle.get(s_upper)
                                if lc is None: self._crypto_live_candle[s_upper] = {'open': live_price, 'high': live_price, 'low': live_price, 'close': live_price}
                                else: lc['high'], lc['low'], lc['close'] = max(lc['high'], live_price), min(lc['low'], live_price), live_price
                            acc_v, acc_d = self._crypto_volume_acc.get(s_upper, 0.0), self._crypto_delta_acc.get(s_upper, 0.0)
                            norm_vol_c, norm_delta_c = self._normalize_crypto_val(symbol, acc_v, live_price, broker_symbol), self._normalize_crypto_val(symbol, acc_d, live_price, broker_symbol)
                            lc_data, bid_p, ask_p = self._crypto_live_candle.get(s_upper, {}), float(ticker_data.get('bid') or 0), float(ticker_data.get('ask') or 0)
                            event = MarketDataEvent(symbol=symbol, timestamp=now, event_type="TICK", last=live_price, bid=bid_p, ask=ask_p, open=lc_data.get('open', live_price), high=lc_data.get('high', live_price), low=lc_data.get('low', live_price), close=live_price, last_size=0, volume=norm_vol_c, delta=norm_delta_c, side="BUY" if acc_d >= 0 else "SELL", source="CRYPTO")
                            if self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED): self._event_buffer.push(event); self._symbol_buffer.update(event); self._metrics.messages_received += 1; self._metrics.last_message_time = time.time()
                    except: pass
            last_candle_poll = self._last_crypto_candle_poll.get(s_upper, 0)
            if now - last_candle_poll >= 1.0:
                self._last_crypto_candle_poll[s_upper] = now
                try:
                    ohlcv = connector.get_ohlcv(broker_symbol, timeframe="1m", limit=100)
                    if ohlcv:
                        prev_live_ts = self._crypto_delta_bar_ts.get(s_upper, 0)
                        last_emitted = self._crypto_last_emitted_ohlcv_ts.get(s_upper, 0)
                        for i in range(len(ohlcv) - 1):
                            bar = ohlcv[i]; bar_ts = int(float(bar[0]) / 1000.0)
                            if bar_ts > last_emitted:
                                bar_close = float(bar[4]); bar_vol = self._normalize_crypto_val(symbol, float(bar[5]), bar_close, broker_symbol)
                                ev = MarketDataEvent(symbol=symbol, timestamp=bar_ts, event_type="OHLCV", open=float(bar[1]), high=float(bar[2]), low=float(bar[3]), close=bar_close, volume=bar_vol, delta=0.0, source="CRYPTO")
                                self._event_buffer.push(ev); self._symbol_buffer.update(ev); self._crypto_last_emitted_ohlcv_ts[s_upper] = bar_ts
                        latest_bar = ohlcv[-1]; latest_ts, latest_close = int(float(latest_bar[0]) / 1000.0), float(latest_bar[4])
                        if latest_ts > prev_live_ts:
                            self._crypto_delta_acc[s_upper], self._crypto_volume_acc[s_upper], self._crypto_delta_bar_ts[s_upper], self._crypto_live_candle[s_upper] = 0.0, 0.0, latest_ts, {'open': float(latest_bar[1]), 'high': float(latest_bar[2]), 'low': float(latest_bar[3]), 'close': latest_close}
                        lc = self._crypto_live_candle.get(s_upper)
                        if lc: lc['high'], lc['low'] = max(lc['high'], float(latest_bar[2])), min(lc['low'], float(latest_bar[3]))
                        else: self._crypto_live_candle[s_upper] = {'open': float(latest_bar[1]), 'high': float(latest_bar[2]), 'low': float(latest_bar[3]), 'close': latest_close}
                        norm_ex_vol = self._normalize_crypto_val(symbol, float(latest_bar[5]), latest_close, broker_symbol)
                        norm_local_vol, norm_local_delta = self._normalize_crypto_val(symbol, self._crypto_volume_acc.get(s_upper, 0.0), latest_close, broker_symbol), self._normalize_crypto_val(symbol, self._crypto_delta_acc.get(s_upper, 0.0), latest_close, broker_symbol)
                        live_ev = MarketDataEvent(symbol=symbol, timestamp=latest_ts, event_type="OHLCV", open=float(latest_bar[1]), high=float(latest_bar[2]), low=float(latest_bar[3]), close=lc.get('close', latest_close) if lc else latest_close, volume=max(norm_ex_vol, norm_local_vol), delta=norm_local_delta, source="CRYPTO")
                        self._symbol_buffer.update(live_ev)
                        if self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED): self._event_buffer.push(live_ev)
                except: pass
            if should_poll_book: self._poll_crypto_book(symbol, s_upper, broker_symbol, connector, now)
        except: pass

    def _normalize_crypto_val(self, symbol: str, val: float, price: float, broker: str = "") -> float:
        if val is None or val == 0 or price is None or price <= 0: return val or 0.0
        abs_v, broker_l, s_up = abs(val), (broker or "").lower(), symbol.upper()
        if 'blofin' in broker_l or 'okx' in broker_l:
            mult = 1.0
            if 'BTC' in s_up: mult = 0.001
            elif 'ETH' in s_up: mult = 0.01
            elif 'SOL' in s_up: mult = 0.1
            elif 'LTC' in s_up: mult = 0.1
            elif 'XRP' in s_up: mult = 10.0
            elif 'ADA' in s_up: mult = 10.0
            if abs_v >= 1.0 and abs_v == int(abs_v) and (abs_v * price) > 500_000: return val * mult
        notional = abs_v * price
        if notional > 1_500_000 and abs_v == int(abs_v): return val / price
        if notional > 1_500_000:
            potential_base = val / price
            if potential_base < 0.001: return val
            return potential_base
        return val

    def _poll_crypto_book(self, symbol: str, s_upper: str, broker_symbol: str, connector, now: float) -> None:
        depth = self._symbol_depths.get(s_upper, 50)
        valid_limits = [5, 10, 20, 50, 100, 500, 1000]
        binance_limit = next((lim for lim in valid_limits if depth <= lim), 1000)
        req_delay = 0.5 if binance_limit <= 100 else 1.0 if binance_limit <= 500 else 1.5 if binance_limit <= 1000 else 3.0
        if not hasattr(self, '_last_crypto_book_poll_strict'): self._last_crypto_book_poll_strict = {}
        if now - self._last_crypto_book_poll_strict.get(s_upper, 0) < req_delay: return
        self._last_crypto_book_poll_strict[s_upper] = now
        try:
            book = connector.get_book_snapshot(broker_symbol, limit=binance_limit)
            if not book or not book.get("bids") or not book.get("asks"): return
            bids_raw, asks_raw = book.get("bids", []), book.get("asks", [])
            with self._pb_lock:
                if s_upper not in self._persistent_books: self._persistent_books[s_upper] = {"bids": {}, "asks": {}, "last_update": 0}
                pb = self._persistent_books[s_upper]
                for b in bids_raw: pb["bids"][float(b["price"])] = float(b["size"])
                for a in asks_raw: pb["asks"][float(a["price"])] = float(a["size"])
                if bids_raw and asks_raw:
                    try:
                        mid = (float(bids_raw[0]["price"]) + float(asks_raw[0]["price"])) / 2
                        p_min, p_max = mid * 0.7, mid * 1.3
                        pb["bids"] = {p: v for p, v in pb["bids"].items() if p_min <= p and v > 0}
                        pb["asks"] = {p: v for p, v in pb["asks"].items() if p <= p_max and v > 0}
                    except: pass
                pb["last_update"] = time.time()
            snapshot = OrderBookSnapshot(symbol=symbol, bids=[BookLevel(price=b["price"], size=b["size"], count=1) for b in bids_raw], asks=[BookLevel(price=a["price"], size=a["size"], count=1) for a in asks_raw])
            self._symbol_buffer.update_book(snapshot)
            midpoint, spread = (float(bids_raw[0]["price"]) + float(asks_raw[0]["price"])) / 2, float(asks_raw[0]["price"]) - float(bids_raw[0]["price"]) if bids_raw and asks_raw else (0, 0)
            if self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED): self._event_buffer.push(MarketDataEvent(symbol=symbol, timestamp=book.get("timestamp", now), event_type="BOOK_UPDATE", bids=[{"price": b["price"], "size": b["size"], "count": 1} for b in bids_raw], asks=[{"price": a["price"], "size": a["size"], "count": 1} for a in asks_raw], midpoint=midpoint, spread=spread, source="CRYPTO"))
        except: pass

    def _detect_platform(self, symbol: str) -> str:
        s = symbol.upper()
        if any(x in s for x in ["USDT", "USDC", "BTC", "ETH", "SOL", "/USDT", ":USDT"]): return "crypto"
        if self._platform == "tradovate": return "tradovate"
        return "mt5"

    def _try_reconnect(self) -> bool:
        logger.info(f"Intentando reconectar plataforma: {self._platform}"); self._metrics.reconnect_count += 1
        with self._connector_lock:
            if self._platform not in self._connectors:
                try: self._get_connector(self._platform)
                except: return False
            connector = self._connectors.get(self._platform)
            if not connector: return False
            try:
                if self._platform == "mt5":
                    ck = {'path': self._mt5_connect_path} if self._mt5_connect_path else {}
                    if connector.connect(**ck): logger.info(f"Reconexión exitosa para {self._platform}"); return True
                else: self._update_status(FeedStatus.ONLINE); self._metrics.connected_since = time.time(); return True
            except: pass
        return False

    def _update_status(self, new_status: FeedStatus) -> None:
        old_status, self._status, self._metrics.status = self._status, new_status, new_status
        if old_status != new_status:
            logger.info(f"Estado del feed: {old_status.value} -> {new_status.value}")
            for callback in self._status_callbacks:
                try: callback(new_status)
                except: pass

    def _update_latency_metrics(self, latency_ms: float) -> None:
        self._metrics.max_latency_ms, self._metrics.min_latency_ms = max(self._metrics.max_latency_ms, latency_ms), min(self._metrics.min_latency_ms, latency_ms)
        alpha = 0.1; self._metrics.avg_latency_ms = alpha * latency_ms + (1 - alpha) * self._metrics.avg_latency_ms

    @property
    def status(self) -> FeedStatus: return self._status
    @property
    def is_online(self) -> bool: return self._status in (FeedStatus.ONLINE, FeedStatus.DEGRADED)
    @property
    def platform(self) -> str: return self._platform
    @property
    def metrics(self) -> FeedMetrics: return self._metrics
    def get_status(self) -> Dict[str, Any]: return {"status": self._status.value, "is_running": self._running, "metrics": self._metrics.to_dict(), "buffer_metrics": self._event_buffer.get_metrics(), "subscribed_symbols": list(self._symbols)}
    def get_latest_quote(self, symbol: str) -> Optional[Dict[str, Any]]: event = self._symbol_buffer.get_latest(symbol); return event.to_dict() if event else None
    def get_book_snapshot(self, symbol: str, limit: int = 100) -> Optional[Dict[str, Any]]:
        symbol = symbol.upper()
        with self._pb_lock:
            if symbol in self._persistent_books:
                pb = self._persistent_books[symbol]; sb, sa = sorted(pb["bids"].items(), reverse=True), sorted(pb["asks"].items())
                mid = (sb[0][0] + sa[0][0]) / 2 if sb and sa else 0
                return {"symbol": symbol, "timestamp": pb.get("last_update", time.time()), "midpoint": mid, "bids": [{"price": p, "size": v, "count": 1} for p, v in sb[:limit]], "asks": [{"price": p, "size": v, "count": 1} for p, v in sa[:limit]]}
        book = self._symbol_buffer.get_book(symbol); return book.to_dict() if book else None
    def get_recent_trades(self, symbol: str, n: int = 100) -> List[Dict[str, Any]]: return [t.to_dict() for t in self._trade_buffer.get_by_symbol(symbol, n)]
    def get_candles(self, symbol: str, n: int = 100) -> List[Dict[str, Any]]: return [e.to_dict() for e in self._symbol_buffer.get_history(symbol, n) if e.event_type in ("OHLCV", "BAR")]
    def request_depth(self, symbol: str, levels: int) -> None:
        symbol, safe = symbol.upper(), min(50000, max(20, levels))
        if safe != self._symbol_depths.get(symbol, 0): self._symbol_depths[symbol] = safe; logger.info(f"Depth request for {symbol} updated to {safe} levels")
    def subscribe_to_events(self, callback: Callable[[MarketDataEvent], None]) -> None: self._event_buffer.subscribe(callback)
    def unsubscribe_from_events(self, callback: Callable[[MarketDataEvent], None]) -> None: self._event_buffer.unsubscribe(callback)
    def subscribe_to_status(self, callback: Callable[[FeedStatus], None]) -> None:
        if callback not in self._status_callbacks: self._status_callbacks.append(callback)
    def unsubscribe_from_status(self, callback: Callable[[FeedStatus], None]) -> None:
        if callback in self._status_callbacks: self._status_callbacks.remove(callback)


def get_market_data_engine() -> MarketDataEngine:
    return MarketDataEngine()