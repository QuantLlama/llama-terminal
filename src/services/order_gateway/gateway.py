import asyncio
import threading
import time
import logging
import json
import os
from typing import Optional, List, Dict, Callable, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty
from .models import (
    OrderRequest, OrderResponse, OrderStatus, OrderSource,
    OrderSide, OrderType, RejectionReason, GatewayMetrics, RiskLimits
)
from .risk_validator import RiskValidator
from src.services.replication_service import replicate_to_nt8_background
logger = logging.getLogger(__name__)
class OrderGateway:
    _instance: Optional['OrderGateway'] = None
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
        self._active_platform = platform 
        self._config_path = config_path
        self._running = False
        self._should_stop = threading.Event()
        self._risk_validator = RiskValidator(config_path=config_path)
        self._connectors: Dict[str, Any] = {}
        self._connector_lock = threading.Lock()
        self._order_queue: Queue = Queue(maxsize=1000)
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="og_worker")
        self._processor_thread: Optional[threading.Thread] = None
        self._metrics = GatewayMetrics()
        self._latency_samples: List[float] = []
        self._order_callbacks: List[Callable[[OrderResponse], None]] = []
        self._setup_logging()
        self._market_data_engine = None
        logger.info(f"OrderGateway inicializado para plataforma: {platform}")
    def _setup_logging(self):
        log_dir = os.path.join(os.path.dirname(__file__), "../../../logs")
        os.makedirs(log_dir, exist_ok=True)
        json_handler = logging.FileHandler(
            os.path.join(log_dir, "order_gateway.log"),
            encoding='utf-8'
        )
        json_handler.setLevel(logging.DEBUG)
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_entry = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "level": record.levelname,
                    "service": "order-gateway",
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName
                }
                if hasattr(record, 'extra'):
                    log_entry.update(record.extra)
                return json.dumps(log_entry)
        json_handler.setFormatter(JsonFormatter())
        logger.addHandler(json_handler)
        logger.setLevel(logging.DEBUG)
    def _get_connector(self, platform: str, account_id: str = None):
        with self._connector_lock:
            platform = platform.lower()
            if platform == "nt8": platform = "tradovate"
            conn_key = f"{platform}_{account_id}" if account_id else platform
            if conn_key not in self._connectors:
                try:
                    if platform == "mt5":
                        from src.live.connector import get_mt5_connector
                        self._connectors[conn_key] = get_mt5_connector()
                    elif platform == "crypto":
                        from src.live.crypto_connector import get_connector
                        if not account_id:
                            from src.services.crypto_manager import get_crypto_manager
                            accounts = get_crypto_manager().get_accounts()
                            if accounts: account_id = accounts[0]['id']
                        if account_id:
                            self._connectors[conn_key] = get_connector(account_id)
                    elif platform == "tradovate":
                        from src.live.tradovate_connector import get_tradovate_connector
                        if not account_id:
                            from src.services.tradovate_manager import get_tradovate_manager
                            accounts = get_tradovate_manager().get_accounts()
                            if accounts: account_id = accounts[0]['id']
                        if account_id:
                            self._connectors[conn_key] = get_tradovate_connector(account_id)
                    else:
                        raise ValueError(f"Plataforma no soportada en Gateway: {platform}")
                except Exception as e:
                    logger.error(f"Error al inicializar conector para {platform}: {e}")
                    return None
            return self._connectors.get(conn_key)
    def set_market_data_engine(self, engine) -> None:
        self._market_data_engine = engine
    def start(self) -> bool:
        if self._running:
            logger.warning("OrderGateway ya está corriendo")
            return True
        logger.info("Iniciando OrderGateway...")
        self._should_stop.clear()
        self._running = True
        self._processor_thread = threading.Thread(
            target=self._process_orders,
            name="OG_Processor",
            daemon=True
        )
        self._processor_thread.start()
        logger.info("OrderGateway iniciado")
        return True
    def stop(self) -> None:
        if not self._running:
            return
        logger.info("Deteniendo OrderGateway...")
        self._should_stop.set()
        self._running = False
        if self._processor_thread and self._processor_thread.is_alive():
            self._processor_thread.join(timeout=5.0)
        with self._connector_lock:
            for name, connector in self._connectors.items():
                try:
                    connector.shutdown()
                except:
                    pass
            self._connectors.clear()
        logger.info("OrderGateway detenido")
    def submit_order(self, order: OrderRequest) -> OrderResponse:
        start_time = time.time()
        self._metrics.total_orders_received += 1
        logger.info(
            f"Orden recibida: {order.symbol} {order.side.value} {order.quantity} "
            f"[{order.source.value}] - ID: {order.client_order_id}"
        )
        check_platform = "tradovate" if order.platform.lower() == "nt8" else order.platform.lower()
        if check_platform != self._active_platform.lower():
            return self._create_rejection(
                order, RejectionReason.UNKNOWN,
                f"Platform mismatch: Order is {order.platform} but system is locked to {self._active_platform}",
                start_time
            )
        if self._market_data_engine and not self._market_data_engine.is_online:
            return self._create_rejection(
                order, RejectionReason.FEED_OFFLINE,
                "Market data feed está offline", start_time
            )
        current_price = None
        try:
            connector = self._get_connector(order.platform, order.account_id)
            if connector and connector.connect():
                current_price = connector.get_current_price(order.symbol)
                if order.platform.lower() == "crypto" and hasattr(connector, "get_order_size_rules"):
                    rules = connector.get_order_size_rules(order.symbol)
                    min_amount = float(rules.get("min_amount") or 0.0)
                    step = float(rules.get("step") or 0.0)
                    contract_size = float(rules.get("contract_size") or 1.0)
                    qty = float(order.quantity)

                    # Normalize user-entered size against the exchange's own rules.
                    # If the user enters a small fractional size, treat it as
                    # underlying units and translate to contracts when needed.
                    if qty > 0 and contract_size > 0 and min_amount > 0 and qty < min_amount:
                        qty = qty / contract_size

                    if step > 0:
                        qty = round(qty / step) * step

                    if min_amount > 0 and qty < min_amount:
                        qty = min_amount

                    order.quantity = qty
        except Exception as e:
            logger.warning(f"No se pudo obtener precio actual: {e}")
        validation_start = time.time()
        validation_result = self._risk_validator.validate(order, current_price)
        validation_latency = (time.time() - validation_start) * 1000
        if not validation_result.is_valid:
            return self._create_rejection(
                order, validation_result.rejection_reason,
                validation_result.message, start_time, validation_latency
            )
        execution_start = time.time()
        response = self._execute_order(order)
        execution_latency = (time.time() - execution_start) * 1000
        total_latency = (time.time() - start_time) * 1000
        response.validation_latency_ms = validation_latency
        response.execution_latency_ms = execution_latency
        response.total_latency_ms = total_latency
        self._update_metrics(order, response, total_latency)
        if response.success:
            self._risk_validator.record_order(order)
        self._notify_callbacks(response)
        status = "OK" if response.success else "FAILED"
        logger.info(
            f"Orden {status}: {order.client_order_id} - "
            f"Latencia: V={validation_latency:.1f}ms E={execution_latency:.1f}ms T={total_latency:.1f}ms"
        )
        return response
    async def submit_order_async(self, order: OrderRequest) -> OrderResponse:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self.submit_order, order)
    def _execute_order(self, order: OrderRequest) -> OrderResponse:
        try:
            connector = self._get_connector(order.platform, order.account_id)
            if not connector or not connector.connect():
                return OrderResponse(
                    success=False,
                    client_order_id=order.client_order_id,
                    symbol=order.symbol,
                    side=order.side.value,
                    quantity=order.quantity,
                    status=OrderStatus.FAILED,
                    source=order.source,
                    rejection_reason=RejectionReason.CONNECTOR_ERROR,
                    error_message=f"No se pudo conectar a {order.platform}"
                )
            side_str = order.side.value if isinstance(order.side, OrderSide) else order.side
            mode_str = order.order_type.value if hasattr(order.order_type, 'value') else order.order_type
            result = connector.place_order(
                symbol=order.symbol,
                order_type=side_str,
                volume=order.quantity,
                price=order.price if order.order_type != OrderType.MARKET else None,
                sl=order.sl,
                tp=order.tp,
                mode=mode_str
            )
            if result:
                if order.platform == "mt5" and order.side in (OrderSide.BUY, OrderSide.SELL):
                    try:
                        replicate_to_nt8_background(
                            symbol=order.symbol,
                            action=order.side.value,
                            volume=order.quantity,
                            sl=order.sl,
                            tp=order.tp,
                            price=order.price or 0.0,
                            order_type=order.order_type.value if hasattr(order.order_type, 'value') else order.order_type
                        )
                    except Exception as mirror_err:
                        logger.error(f"Mirroring failed: {mirror_err}")
                return OrderResponse(
                    success=True,
                    order_id=str(getattr(result, 'order', '')),
                    client_order_id=order.client_order_id,
                    symbol=order.symbol,
                    side=side_str,
                    quantity=order.quantity,
                    filled_qty=order.quantity,  
                    avg_price=order.price or 0.0,
                    status=OrderStatus.FILLED,
                    source=order.source
                )
            else:
                return OrderResponse(
                    success=False,
                    client_order_id=order.client_order_id,
                    symbol=order.symbol,
                    side=side_str,
                    quantity=order.quantity,
                    status=OrderStatus.FAILED,
                    source=order.source,
                    rejection_reason=RejectionReason.CONNECTOR_ERROR,
                    error_message="Orden rechazada por el broker"
                )
        except Exception as e:
            logger.error(f"Error ejecutando orden: {e}")
            return OrderResponse(
                success=False,
                client_order_id=order.client_order_id,
                symbol=order.symbol,
                status=OrderStatus.FAILED,
                source=order.source,
                rejection_reason=RejectionReason.UNKNOWN,
                error_message=str(e)
            )
    def _create_rejection(
        self, order: OrderRequest, reason: RejectionReason,
        message: str, start_time: float, validation_latency: float = 0.0
    ) -> OrderResponse:
        self._metrics.orders_rejected += 1
        return OrderResponse(
            success=False,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side.value if isinstance(order.side, OrderSide) else order.side,
            quantity=order.quantity,
            status=OrderStatus.REJECTED,
            source=order.source,
            rejection_reason=reason,
            error_message=message,
            validation_latency_ms=validation_latency,
            total_latency_ms=(time.time() - start_time) * 1000
        )
    def _update_metrics(self, order: OrderRequest, response: OrderResponse, latency_ms: float) -> None:
        if response.success:
            self._metrics.orders_executed += 1
        else:
            self._metrics.orders_failed += 1
        if order.source == OrderSource.ALGO:
            self._metrics.algo_orders += 1
        else:
            self._metrics.manual_orders += 1
        self._metrics.orders_validated += 1
        self._metrics.last_order_time = time.time()
        self._latency_samples.append(latency_ms)
        if len(self._latency_samples) > 100:
            self._latency_samples = self._latency_samples[-100:]
        if self._latency_samples:
            self._metrics.avg_total_latency_ms = sum(self._latency_samples) / len(self._latency_samples)
        recent_count = self._metrics.orders_validated
        elapsed = time.time() - (self._metrics.last_order_time - 60) if self._metrics.last_order_time else 1
        self._metrics.orders_per_second = recent_count / max(elapsed, 1)
    def _process_orders(self) -> None:
        while not self._should_stop.is_set():
            try:
                order = self._order_queue.get(timeout=0.1)
                self.submit_order(order)
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Error en procesamiento de cola: {e}")
    def _notify_callbacks(self, response: OrderResponse) -> None:
        for callback in self._order_callbacks:
            try:
                callback(response)
            except Exception as e:
                logger.error(f"Error en callback de orden: {e}")
    @property
    def is_running(self) -> bool:
        return self._running
    @property
    def metrics(self) -> GatewayMetrics:
        return self._metrics
    def get_status(self) -> Dict[str, Any]:
        return {
            "is_running": self._running,
            "queue_size": self._order_queue.qsize(),
            "metrics": self._metrics.to_dict(),
            "risk_stats": self._risk_validator.get_stats()
        }
    def get_risk_limits(self) -> Dict[str, Any]:
        return self._risk_validator.get_limits().to_dict()
    def set_risk_limits(self, limits: Dict[str, Any]) -> None:
        self._risk_validator.set_limits(RiskLimits.from_dict(limits))
    def queue_order(self, order: OrderRequest) -> bool:
        try:
            self._order_queue.put_nowait(order)
            return True
        except:
            logger.error("Cola de órdenes llena")
            return False
    def subscribe_to_orders(self, callback: Callable[[OrderResponse], None]) -> None:
        if callback not in self._order_callbacks:
            self._order_callbacks.append(callback)
    def unsubscribe_from_orders(self, callback: Callable[[OrderResponse], None]) -> None:
        if callback in self._order_callbacks:
            self._order_callbacks.remove(callback)
    def update_pnl(self, pnl_change: float) -> None:
        self._risk_validator.update_pnl(pnl_change)
        self._metrics.daily_pnl += pnl_change
    def switch_platform(self, new_platform: str) -> bool:
        if new_platform not in ("mt5", "crypto", "tradovate", "nt8"):
            logger.error(f"Cannot switch to unsupported platform: {new_platform}. Supported: MT5, Crypto, Tradovate, NT8.")
            return False
        self._active_platform = "tradovate" if new_platform == "nt8" else new_platform
        logger.info(f"OrderGateway platform switched to: {self._active_platform}")
        return True
def get_order_gateway() -> OrderGateway:
    return OrderGateway()
