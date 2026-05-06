import sys
import time
import threading
import logging
import json
import os
from enum import Enum
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
try:
    # ── Try to add torch/lib to DLL path for Windows/Wine ──
    if sys.platform == "win32":
        torch_lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../venv/Lib/site-packages/torch/lib")
        if os.path.exists(torch_lib):
            os.environ['PATH'] = torch_lib + os.pathsep + os.environ.get('PATH', '')
            if hasattr(os, 'add_dll_directory'):
                try:
                    os.add_dll_directory(torch_lib)
                except Exception:
                    pass
    import torch
    HAS_TORCH = True
except (ImportError, OSError) as e:
    logger.warning(f"AVISO: No se pudo cargar 'torch' ({e}). Las funciones de IA estarán desactivadas en este proceso.")
    HAS_TORCH = False
    torch = None

import numpy as np
import pandas as pd
logger = logging.getLogger(__name__)
class AlgoStatus(str, Enum):
    STOPPED = "STOPPED"      
    RUNNING = "RUNNING"      
    LIVE = "LIVE"            
    ERROR = "ERROR"          
@dataclass
class AlgoMetrics:
    status: AlgoStatus = AlgoStatus.STOPPED
    signals_generated: int = 0
    orders_sent: int = 0
    orders_filled: int = 0
    last_signal_time: float = 0.0
    last_signal: str = "HOLD"
    win_rate: float = 0.0
    current_position: str = "FLAT"  
    daily_pnl: float = 0.0
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "signals_generated": self.signals_generated,
            "orders_sent": self.orders_sent,
            "orders_filled": self.orders_filled,
            "last_signal_time": self.last_signal_time,
            "last_signal": self.last_signal,
            "win_rate": round(self.win_rate, 2),
            "current_position": self.current_position,
            "daily_pnl": round(self.daily_pnl, 2)
        }
class AlgoEngine:
    _instance: Optional['AlgoEngine'] = None
    _lock = threading.Lock()
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance
    def __init__(self, ticker: str = None, timeframe: str = "1m"):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        self._ticker = ticker
        self._timeframe = timeframe
        self._status = AlgoStatus.STOPPED
        self._live_mode = False  
        self._should_stop = threading.Event()
        self._model = None
        self._scaler = None
        self._device = None
        self._seq_length = 60
        self._market_data_engine = None
        self._order_gateway = None
        self._config: Dict[str, Any] = self._load_default_config()
        self._algo_thread: Optional[threading.Thread] = None
        self._metrics = AlgoMetrics()
        self._signal_callbacks: List[Callable[[str, float, Dict], None]] = []
        self._last_trade_time: float = 0
        self._consecutive_signals: int = 0
        self._last_raw_signal: str = "HOLD"
        self._setup_logging()
        logger.info(f"AlgoEngine inicializado - Ticker: {ticker}, TF: {timeframe}")
    def _setup_logging(self):
        from src.services.database import get_logs_dir
        log_dir = get_logs_dir()
        json_handler = logging.FileHandler(
            os.path.join(log_dir, "algo_engine.log"),
            encoding='utf-8'
        )
        json_handler.setLevel(logging.DEBUG)
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_entry = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "level": record.levelname,
                    "service": "algo-engine",
                    "message": record.getMessage(),
                    "module": record.module
                }
                return json.dumps(log_entry)
        json_handler.setFormatter(JsonFormatter())
        logger.addHandler(json_handler)
        logger.setLevel(logging.DEBUG)
    def _load_default_config(self) -> Dict[str, Any]:
        return {
            "automation_enabled": False,  
            "volume": 1.0,
            "max_daily_loss": 500.0,
            "daily_profit_target": 100.0,
            "max_trades_per_day": 5,
            "start_hour": "09:30",
            "end_hour": "16:00",
            "min_adx": 15,
            "rsi_upper": 70,
            "rsi_lower": 30,
            "consecutive_signals": 1,
            "cooldown_seconds": 300
        }
    def set_market_data_engine(self, engine) -> None:
        self._market_data_engine = engine
        logger.info("MarketDataEngine conectado al AlgoEngine")
    def set_order_gateway(self, gateway) -> None:
        self._order_gateway = gateway
        logger.info("OrderGateway conectado al AlgoEngine")
    def load_model(self, ticker: str = None, timeframe: str = None) -> bool:
        ticker = ticker or self._ticker
        timeframe = timeframe or self._timeframe
        if not ticker:
            logger.error("No se especificó ticker para cargar modelo")
            return False
        try:
            safe_ticker = ticker.replace("=", "").replace("-", "")
            from src.services.database import get_outputs_dir
            outputs_dir = get_outputs_dir()
            models_dir = os.path.join(outputs_dir, "models")
            model_path = os.path.join(models_dir, f"{safe_ticker}_{timeframe}_generator.pth")
            scaler_path = os.path.join(models_dir, f"{safe_ticker}_{timeframe}_scaler.pkl")
            config_path = os.path.join(models_dir, f"{safe_ticker}_{timeframe}_config.json")
            if not os.path.exists(model_path):
                model_path = os.path.join(outputs_dir, "generator.pth")
                scaler_path = os.path.join(outputs_dir, "scaler.pkl")
                config_path = os.path.join(outputs_dir, "model_config.json")
            if not os.path.exists(model_path):
                logger.error(f"Modelo no encontrado: {model_path}")
                return False
            if not HAS_TORCH:
                logger.error("No se puede cargar el modelo: 'torch' no está disponible en este entorno.")
                return False
            import joblib
            from src.models.generator import Generator
            self._scaler = joblib.load(scaler_path)
            hidden_dim = 128
            num_layers = 2
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    model_config = json.load(f)
                    hidden_dim = model_config.get("hidden_dim", 128)
                    num_layers = model_config.get("num_layers", 2)
                    self._seq_length = model_config.get("seq_length", 60)
            self._device = get_best_device()
            INPUT_DIM = 7
            if HAS_TORCH:
                self._model = Generator(INPUT_DIM, hidden_dim, num_layers, INPUT_DIM).to(self._device)
                self._model.load_state_dict(torch.load(model_path, map_location=self._device, weights_only=True))
                self._model.eval()
            else:
                return False
            self._ticker = ticker
            self._timeframe = timeframe
            logger.info(f"Modelo cargado: {ticker} ({timeframe})")
            return True
        except Exception as e:
            logger.error(f"Error cargando modelo: {e}")
            return False
    def start(self, live_mode: bool = False) -> bool:
        if self._status in (AlgoStatus.RUNNING, AlgoStatus.LIVE):
            logger.warning("AlgoEngine ya está corriendo")
            return True
        if not self._market_data_engine:
            logger.error("MarketDataEngine no está configurado")
            return False
        if not self._order_gateway:
            logger.error("OrderGateway no está configurado")
            return False
        if not self._model:
            logger.error("Modelo no cargado. Llame a load_model() primero")
            return False
        if not self._market_data_engine.is_online:
            logger.warning("MarketDataEngine no está online - El algoritmo esperará datos")
        self._live_mode = live_mode
        self._should_stop.clear()
        self._algo_thread = threading.Thread(
            target=self._algo_loop,
            name="AlgoEngine_Loop",
            daemon=True
        )
        self._algo_thread.start()
        self._status = AlgoStatus.LIVE if live_mode else AlgoStatus.RUNNING
        self._metrics.status = self._status
        mode_str = "LIVE (enviando órdenes)" if live_mode else "RUNNING (solo señales)"
        logger.info(f"AlgoEngine iniciado en modo {mode_str}")
        return True
    def stop(self) -> None:
        if self._status == AlgoStatus.STOPPED:
            return
        logger.info("Deteniendo AlgoEngine...")
        self._should_stop.set()
        self._live_mode = False
        if self._algo_thread and self._algo_thread.is_alive():
            self._algo_thread.join(timeout=5.0)
        self._status = AlgoStatus.STOPPED
        self._metrics.status = self._status
        logger.info("AlgoEngine detenido - Feed y OrderGateway siguen activos")
    def set_live_mode(self, enabled: bool) -> None:
        self._live_mode = enabled
        self._config["automation_enabled"] = enabled
        if self._status in (AlgoStatus.RUNNING, AlgoStatus.LIVE):
            self._status = AlgoStatus.LIVE if enabled else AlgoStatus.RUNNING
            self._metrics.status = self._status
        mode = "LIVE" if enabled else "SIGNAL_ONLY"
        logger.info(f"Modo cambiado a: {mode}")
    def _algo_loop(self) -> None:
        logger.info("Iniciando loop del algoritmo...")
        while not self._should_stop.is_set():
            try:
                market_data = self._get_market_data()
                if market_data is None:
                    time.sleep(0.5)
                    continue
                signal, confidence, metadata = self._generate_signal(market_data)
                if signal != "HOLD":
                    self._metrics.signals_generated += 1
                    self._metrics.last_signal = signal
                    self._metrics.last_signal_time = time.time()
                    self._notify_signal(signal, confidence, metadata)
                    if self._live_mode and self._can_trade():
                        self._send_order(signal, metadata)
                self._update_status_file(signal, metadata)
                time.sleep(0.5)  
            except Exception as e:
                logger.error(f"Error en algo loop: {e}")
                self._status = AlgoStatus.ERROR
                self._metrics.status = self._status
                time.sleep(1)
    def _get_market_data(self) -> Optional[pd.DataFrame]:
        if not self._market_data_engine or not self._market_data_engine.is_online:
            return None
        events = self._market_data_engine._symbol_buffer.get_history(
            self._ticker, n=self._seq_length + 100
        )
        if len(events) < self._seq_length:
            return None
        data = []
        for e in events:
            if e.event_type == "OHLCV":
                data.append({
                    'time': datetime.fromtimestamp(e.timestamp),
                    'Open': e.open,
                    'High': e.high,
                    'Low': e.low,
                    'Close': e.close,
                    'Volume': e.volume
                })
        if len(data) < self._seq_length:
            return None
        return pd.DataFrame(data)
    def _generate_signal(self, df: pd.DataFrame) -> tuple:
        try:
            from src.analysis.market_filter import MarketFilter
            market_filter = MarketFilter()
            df = market_filter.calculate_indicators(df)
            df = df.dropna()
            if len(df) < self._seq_length:
                return "HOLD", 0.0, {}
            df['Log_Ret_Close'] = np.log(df['Close'] / df['Close'].shift(1))
            df['Log_Ret_High'] = np.log(df['High'] / df['High'].shift(1))
            df['Log_Ret_Low'] = np.log(df['Low'] / df['Low'].shift(1))
            df['Log_Vol'] = np.log1p(df['Volume'])
            df = df.dropna()
            if len(df) < self._seq_length:
                return "HOLD", 0.0, {}
            features = ['Log_Ret_Close', 'Log_Ret_High', 'Log_Ret_Low', 'Log_Vol', 'RSI', 'ADX', 'ATR']
            if not HAS_TORCH or self._model is None:
                return "HOLD", 0.0, {}
                
            last_sequence = df.tail(self._seq_length)[features].values
            last_sequence_scaled = self._scaler.transform(last_sequence)
            input_tensor = torch.FloatTensor(last_sequence_scaled).unsqueeze(0).to(self._device)
            with torch.no_grad():
                prediction_seq = self._model(input_tensor)
                prediction_scaled = prediction_seq[:, -1, :].cpu().numpy()
            dummy_pred = np.zeros((1, self._scaler.n_features_in_))
            dummy_pred[:, 0] = prediction_scaled[:, 0]
            prediction_real = self._scaler.inverse_transform(dummy_pred)
            predicted_log_return = prediction_real[0, 0]
            current_price = df['Close'].iloc[-1]
            threshold = 0.0001
            signal = "HOLD"
            confidence = abs(predicted_log_return) / threshold if threshold > 0 else 0
            if predicted_log_return > threshold:
                signal = "BUY"
            elif predicted_log_return < -threshold:
                signal = "SELL"
            required_consecutive = self._config.get("consecutive_signals", 1)
            if required_consecutive > 1:
                if signal == self._last_raw_signal and signal != "HOLD":
                    self._consecutive_signals += 1
                else:
                    self._consecutive_signals = 1
                    self._last_raw_signal = signal
                if self._consecutive_signals < required_consecutive:
                    signal = "HOLD"
            if signal != "HOLD":
                is_valid, msg = market_filter.check_conditions(df, signal, self._config)
                if not is_valid:
                    signal = "HOLD"
            metadata = {
                "current_price": float(current_price),
                "predicted_return": float(predicted_log_return),
                "rsi": float(df['RSI'].iloc[-1]) if 'RSI' in df.columns else 50.0,
                "adx": float(df['ADX'].iloc[-1]) if 'ADX' in df.columns else 20.0,
                "atr": float(df['ATR'].iloc[-1]) if 'ATR' in df.columns else 0.0
            }
            return signal, confidence, metadata
        except Exception as e:
            logger.error(f"Error generando señal: {e}")
            return "HOLD", 0.0, {}
    def _can_trade(self) -> bool:
        now = datetime.now()
        time_str = now.strftime("%H:%M")
        if not (self._config["start_hour"] <= time_str <= self._config["end_hour"]):
            return False
        cooldown = self._config.get("cooldown_seconds", 300)
        if (time.time() - self._last_trade_time) < cooldown:
            return False
        return True
    def _send_order(self, signal: str, metadata: Dict[str, Any]) -> None:
        if not self._order_gateway:
            logger.error("OrderGateway no configurado")
            return
        from src.services.order_gateway.models import OrderRequest, OrderSource, OrderSide, OrderType
        current_price = metadata.get("current_price", 0)
        atr = metadata.get("atr", current_price * 0.001)
        sl_points = atr * 2.0
        tp_points = atr * 3.0
        if signal == "BUY":
            sl = current_price - sl_points
            tp = current_price + tp_points
            side = OrderSide.BUY
        else:
            sl = current_price + sl_points
            tp = current_price - tp_points
            side = OrderSide.SELL
        order = OrderRequest(
            symbol=self._ticker,
            side=side,
            quantity=float(self._config.get("volume", 1.0)),
            order_type=OrderType.MARKET,
            sl=sl,
            tp=tp,
            source=OrderSource.ALGO,  
            comment="AlgoEngine-Auto"
        )
        logger.info(f"Enviando orden ALGO: {signal} {self._ticker}")
        response = self._order_gateway.submit_order(order)
        if response.success:
            self._metrics.orders_sent += 1
            self._metrics.orders_filled += 1
            self._last_trade_time = time.time()
            logger.info(f"Orden ALGO ejecutada: {response.order_id}")
        else:
            logger.warning(f"Orden ALGO rechazada: {response.error_message}")
    def _notify_signal(self, signal: str, confidence: float, metadata: Dict) -> None:
        for callback in self._signal_callbacks:
            try:
                callback(signal, confidence, metadata)
            except Exception as e:
                logger.error(f"Error en callback de señal: {e}")
    def _update_status_file(self, signal: str, metadata: Dict) -> None:
        try:
            status = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ticker": self._ticker,
                "signal": signal,
                "algo_status": self._status.value,
                "live_mode": self._live_mode,
                "metrics": self._metrics.to_dict(),
                "metadata": metadata,
                "config": self._config
            }
            from src.services.database import get_outputs_dir
            status_path = os.path.join(get_outputs_dir(), "live_status.json")
            temp_path = status_path + ".tmp"
            with open(temp_path, "w") as f:
                json.dump(status, f, default=str)
            os.replace(temp_path, status_path)
        except Exception as e:
            logger.error(f"Error actualizando status: {e}")
    @property
    def status(self) -> AlgoStatus:
        return self._status
    @property
    def is_live(self) -> bool:
        return self._live_mode
    @property
    def metrics(self) -> AlgoMetrics:
        return self._metrics
    def get_status(self) -> Dict[str, Any]:
        return {
            "status": self._status.value,
            "is_live": self._live_mode,
            "ticker": self._ticker,
            "timeframe": self._timeframe,
            "metrics": self._metrics.to_dict(),
            "config": self._config
        }
    def update_config(self, config: Dict[str, Any]) -> None:
        self._config.update(config)
        self._live_mode = config.get("automation_enabled", self._live_mode)
        logger.info("Configuración actualizada")
    def subscribe_to_signals(self, callback: Callable[[str, float, Dict], None]) -> None:
        if callback not in self._signal_callbacks:
            self._signal_callbacks.append(callback)
    def unsubscribe_from_signals(self, callback: Callable[[str, float, Dict], None]) -> None:
        if callback in self._signal_callbacks:
            self._signal_callbacks.remove(callback)
def get_algo_engine() -> AlgoEngine:
    return AlgoEngine()