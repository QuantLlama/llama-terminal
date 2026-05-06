import asyncio
import json
import time
import threading
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
logger = logging.getLogger(__name__)
from fastapi import (
    APIRouter,
    Body,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field
from src.platform.api.utils import sanitize_float, resolve_symbol
router = APIRouter(prefix="/api/v2", tags=["Platform Services"])
class FeedSubscriptionRequest(BaseModel):
    symbols: List[str] = Field(..., description="Lista de símbolos a suscribir")
class ManualOrderRequest(BaseModel):
    symbol: str
    side: str = Field(..., pattern="^(BUY|SELL)$")
    quantity: float = Field(..., gt=0)
    order_type: str = Field(default="MKT", pattern="^(MKT|LIMIT|STOP)$")
    price: Optional[float] = 0.0
    sl: Optional[float] = 0.0
    tp: Optional[float] = 0.0
    platform: str = Field(default="mt5", pattern="^(mt5|crypto|tradovate)$")
class AlgoStartRequest(BaseModel):
    ticker: str
    timeframe: str = "1m"
    live_mode: bool = False
class RiskLimitsUpdate(BaseModel):
    max_position_size: Optional[float] = None
    max_daily_loss: Optional[float] = None
    max_orders_per_day: Optional[int] = None
    trading_start_hour: Optional[str] = None
    trading_end_hour: Optional[str] = None
class PlatformSwitchRequest(BaseModel):
    platform: str = Field(..., pattern="^(mt5|crypto|tradovate)$")
class LlamaToggleRequest(BaseModel):
    type: str
    active: bool
_market_data_engine = None
_order_gateway = None
_algo_engine = None
_big_llama_engine = None
_inbalance_llama_engine = None
_caza_llama_engine = None
def init_services(mde, og, ae, ble=None, ile=None, cle=None):
    global _market_data_engine, _order_gateway, _algo_engine, _big_llama_engine, _inbalance_llama_engine, _caza_llama_engine
    _market_data_engine = mde
    _order_gateway = og
    _algo_engine = ae
    _big_llama_engine = ble
    _inbalance_llama_engine = ile
    _caza_llama_engine = cle
async def ensure_market_data_engine():
    global _market_data_engine
    if _market_data_engine is None:
        print("INFO: MarketDataEngine no inicializado. Iniciando de forma diferida (Lacy-Load)...")
        from src.services.market_data_engine.engine import MarketDataEngine
        _market_data_engine = MarketDataEngine(platform="mt5")
    if not getattr(_market_data_engine, '_running', False):
        if not getattr(_market_data_engine, '_starting', False):
            print("INFO: Arrancando MarketDataEngine en segundo plano...")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _market_data_engine.start)
    return _market_data_engine
async def ensure_order_gateway():
    global _order_gateway
    if _order_gateway is None:
        print("INFO: OrderGateway no inicializado. Iniciando de forma diferida...")
        from src.services.order_gateway import OrderGateway
        _order_gateway = OrderGateway(platform="mt5")
        mde = await ensure_market_data_engine()
        _order_gateway.set_market_data_engine(mde)
        _order_gateway.start()
    return _order_gateway
async def ensure_algo_engine():
    global _algo_engine
    if _algo_engine is None:
        print("INFO: AlgoEngine no inicializado. Iniciando de forma diferida...")
        from src.services.algo_engine import AlgoEngine
        _algo_engine = AlgoEngine()
        mde = await ensure_market_data_engine()
        og = await ensure_order_gateway()
        _algo_engine.set_market_data_engine(mde)
        _algo_engine.set_order_gateway(og)
    return _algo_engine
_active_connections = 0
_shutdown_task = None
def register_connection():
    global _active_connections, _shutdown_task
    _active_connections += 1
    if _shutdown_task:
        _shutdown_task.cancel()
        _shutdown_task = None
    print(f"WS_STATUS: Nueva conexión detectada. Total activas: {_active_connections}")
def unregister_connection():
    global _active_connections, _shutdown_task
    if _active_connections > 0:
        _active_connections -= 1
    print(f"WS_STATUS: Conexión cerrada. Restantes: {_active_connections}")
    if _active_connections == 0:
        if _shutdown_task:
            _shutdown_task.cancel()  
        try:
            loop = asyncio.get_event_loop()
            _shutdown_task = loop.create_task(_check_auto_shutdown())
        except Exception as e:
            print(f"ERROR: No se pudo crear tarea de auto-apagado: {e}")
async def _check_auto_shutdown():
    print("WS_STATUS: Iniciando cuenta regresiva para auto-apagado (300s)...")
    await asyncio.sleep(300)
    if _active_connections == 0:
        print("CRITICAL: No hay navegadores conectados. APAGANDO SISTEMA...")
        try:
            await shutdown_services()
        except Exception as e:
            print(f"ERROR durante apagado automático: {e}")
        print("INFO: Sistema apagado. Finalizando proceso de Python.")
        import os
        import subprocess
        import sys
        try:
            kwargs = {}
            if sys.platform == "win32":
                startupinfo_kill = subprocess.STARTUPINFO()
                startupinfo_kill.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo_kill.wShowWindow = 0
                kwargs["startupinfo"] = startupinfo_kill
                kwargs["creationflags"] = 0x08000000
                subprocess.run(
                    ["taskkill", "/F", "/IM", "terminal64.exe"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **kwargs
                )
            # Else branch skipped for terminal64 to avoid killall breaking under Wine
            pid = os.getpid()
            if sys.platform == "win32":
                subprocess.Popen(
                    ["taskkill", "/F", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **kwargs
                )
            else:
                subprocess.Popen(
                    ["kill", "-9", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except:
            pass
        os._exit(0)
    else:
        print(
            f"WS_STATUS: Auto-apagado cancelado. {_active_connections} navegadores reconectados."
        )
async def _safety_timeout_task():
    pass
def get_platform_health():
    global _market_data_engine, _order_gateway, _algo_engine
    mde_status = "OFFLINE"
    if _market_data_engine:
        try:
            mde_status = _market_data_engine.status.value
        except:
            mde_status = "ERROR"
    splash_status = "stopped"
    if mde_status in ["ONLINE", "DEGRADED"]:
        splash_status = "connected"
    elif mde_status in ["CONNECTING", "RECONNECTING"]:
        splash_status = "running"
    elif mde_status == "OFFLINE":
        splash_status = "stopped"
    ready = True
    return {
        "ready_for_ui": ready,
        "mt5_status": splash_status,
        "services": {
            "market_data": mde_status,
            "order_gateway": "running"
            if (_order_gateway and _order_gateway.is_running)
            else "stopped",
            "algo_engine": _algo_engine.status.value if _algo_engine else "stopped",
            "big_llama": "active" if (_big_llama_engine and _big_llama_engine._active) else "inactive",
            "inbalance_llama": "active" if (_inbalance_llama_engine and _inbalance_llama_engine._active) else "inactive",
            "caza_llama": "active" if (_caza_llama_engine and _caza_llama_engine._active) else "inactive",
        },
        "timestamp": time.time(),
    }
@router.get("/feed/status")
async def get_feed_status():
    mde = await ensure_market_data_engine()
    if not mde:
        raise HTTPException(status_code=503, detail="MarketDataEngine no disponible")
    return mde.get_status()
@router.post("/feed/subscribe")
async def subscribe_symbols(request: FeedSubscriptionRequest):
    mde = await ensure_market_data_engine()
    if not mde:
        raise HTTPException(status_code=503, detail="MarketDataEngine no disponible")
    mde.subscribe(request.symbols)
    return {"status": "subscribed", "symbols": request.symbols}
@router.post("/feed/unsubscribe")
async def unsubscribe_symbols(request: FeedSubscriptionRequest):
    mde = await ensure_market_data_engine()
    if not mde:
        raise HTTPException(status_code=503, detail="MarketDataEngine no disponible")
    mde.unsubscribe(request.symbols)
    return {"status": "unsubscribed", "symbols": request.symbols}
@router.post("/feed/switch-platform")
async def switch_platform(request: PlatformSwitchRequest):
    mde = await ensure_market_data_engine()
    if not mde:
        raise HTTPException(status_code=503, detail="MarketDataEngine no disponible")
    try:
        success = await asyncio.to_thread(_market_data_engine.switch_platform, request.platform)
        if success:
            if hasattr(request, 'app') and hasattr(request.app, 'state'):
                request.app.state.last_platform = request.platform
            return {"status": "switched", "platform": request.platform}
        else:
             raise HTTPException(status_code=500, detail="Error switching platform or platform already active")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/debug/engine")
async def debug_engine():
    if not _market_data_engine:
        return {"error": "Engine not created"}
    
    mde = _market_data_engine
    metrics = mde.get_metrics() if hasattr(mde, 'get_metrics') else {}
    
    return {
        "running": getattr(mde, '_running', False),
        "starting": getattr(mde, '_starting', False),
        "platform": mde.platform,
        "status": mde.status.value,
        "is_online": mde.is_online(),
        "subscribed": list(mde._symbols) if hasattr(mde, '_symbols') else [],
        "messages_received": getattr(mde, '_metrics', None) and getattr(mde._metrics, 'messages_received', 0),
        "last_message_time": getattr(mde, '_metrics', None) and getattr(mde._metrics, 'last_message_time', 0),
        "buffer_size": mde._event_buffer.size() if hasattr(mde, '_event_buffer') else 0,
        "symbols_with_data": list(mde._symbol_buffer.get_all_symbols()) if hasattr(mde, '_symbol_buffer') else [],
        "crypto_live_candles": list(mde._crypto_live_candle.keys()) if hasattr(mde, '_crypto_live_candle') else [],
        "timestamp": time.time()
    }
@router.get("/feed/quote/{symbol}")
async def get_quote(symbol: str):
    if not _market_data_engine:
        raise HTTPException(status_code=503, detail="MarketDataEngine no inicializado")
    quote = _market_data_engine.get_latest_quote(symbol)
    if not quote:
        raise HTTPException(status_code=404, detail=f"No hay datos para {symbol}")
    return quote
@router.get("/feed/book/{symbol:path}")
@router.get("/feed/dom/{symbol:path}")
async def get_book_or_dom(symbol: str, levels: int = Query(default=20, gt=0, le=50000)):
    try:
        mde = await ensure_market_data_engine()
        if not mde or not getattr(mde, '_running', False):
            status = "waiting_for_engine"
            if mde and not getattr(mde, '_running', False):
                status = "engine_initializing"
            return {"status": status}
        target_platform = mde._detect_platform(symbol) if hasattr(mde, '_detect_platform') else "mt5"
        if target_platform != "crypto" and mde.platform != target_platform:
            print(f"MDE_SWITCH: Detectado cambio de plataforma para {symbol} -> {target_platform}")
            try:
                success = mde.switch_platform(target_platform)
                if not success:
                    return {"status": "failed_to_switch_platform", "platform": target_platform}
            except Exception as e:
                print(f"MDE_SWITCH: ERROR crítico al cambiar plataforma: {e}")
                return {"status": "failed_to_switch_platform", "error": str(e)}
        book = mde.get_book_snapshot(symbol, limit=levels)
        resolved_symbol = resolve_symbol(symbol)
        if (not book or (not book.get("bids") and not book.get("asks"))) and resolved_symbol != symbol:
            book = mde.get_book_snapshot(resolved_symbol)
        if hasattr(mde, 'subscribe'):
            mde.subscribe([symbol])
            if hasattr(mde, 'request_depth') and levels > 100:
                mde.request_depth(symbol, levels)
            if resolved_symbol != symbol:
                mde.subscribe([resolved_symbol])
                if hasattr(mde, 'request_depth') and levels > 100:
                    mde.request_depth(resolved_symbol, levels)
        if not book or (not book.get("bids") and not book.get("asks")):
            return {"status": "waiting_for_data", "symbol": symbol, "resolved": resolved_symbol}
        return book
    except Exception as e:
        logger.error(f"DOM API ERROR for {symbol}: {e}")
        return {"status": "api_error", "message": str(e), "symbol": symbol}
@router.get("/feed/trades/{symbol}")
async def get_trades(symbol: str, limit: int = Query(default=100, le=1000)):
    mde = await ensure_market_data_engine()
    if not mde:
        raise HTTPException(status_code=503, detail="MarketDataEngine no disponible")
    return mde.get_recent_trades(symbol, limit)
@router.get("/orders/status")
async def get_order_gateway_status():
    og = await ensure_order_gateway()
    if not og:
        raise HTTPException(status_code=503, detail="OrderGateway no disponible")
    return og.get_status()
@router.post("/orders/manual")
async def submit_manual_order(order: ManualOrderRequest):
    og = await ensure_order_gateway()
    if not og:
        raise HTTPException(status_code=503, detail="OrderGateway no disponible")
    mde = await ensure_market_data_engine()
    if mde and not mde.is_online:
        raise HTTPException(
            status_code=503,
            detail="Feed offline - órdenes manuales requieren feed activo",
        )
    from src.services.order_gateway.models import (
        OrderRequest,
        OrderSide,
        OrderSource,
        OrderType,
    )
    request = OrderRequest(
        symbol=order.symbol,
        side=OrderSide(order.side),
        quantity=order.quantity,
        order_type=OrderType(order.order_type),
        price=order.price,
        sl=order.sl,
        tp=order.tp,
        source=OrderSource.MANUAL,  
        platform=order.platform,
        comment="Manual-API",
    )
    response = await og.submit_order_async(request)
    return response.to_dict()
@router.get("/orders/risk-limits")
async def get_risk_limits():
    og = await ensure_order_gateway()
    if not og:
        raise HTTPException(status_code=503, detail="OrderGateway no disponible")
    return og.get_risk_limits()
@router.post("/orders/risk-limits")
async def update_risk_limits(limits: RiskLimitsUpdate):
    og = await ensure_order_gateway()
    if not og:
        raise HTTPException(status_code=503, detail="OrderGateway no disponible")
    updates = {k: v for k, v in limits.model_dump().items() if v is not None}
    current = og.get_risk_limits()
    current.update(updates)
    og.set_risk_limits(current)
    return {"status": "updated", "limits": current}
@router.get("/algo/status")
async def get_algo_status():
    ae = await ensure_algo_engine()
    if not ae:
        raise HTTPException(status_code=503, detail="AlgoEngine no disponible")
    return ae.get_status()
@router.post("/algo/start")
async def start_algo(request: AlgoStartRequest):
    if not _algo_engine.start(live_mode=request.live_mode):
        raise HTTPException(status_code=500, detail="Error iniciando algoritmo")
    mode = "LIVE" if request.live_mode else "SIGNAL_ONLY"
    return {
        "status": "started",
        "mode": mode,
        "ticker": request.ticker,
        "message": "Feed y OrderGateway siguen operativos independientemente",
    }
@router.post("/algo/stop")
async def stop_algo():
    if not _algo_engine:
        raise HTTPException(status_code=503, detail="AlgoEngine no inicializado")
    _algo_engine.stop()
    return {
        "status": "stopped",
        "message": "Algoritmo detenido. Feed y OrderGateway siguen activos para órdenes manuales.",
    }
@router.post("/algo/live-mode")
async def set_live_mode(enabled: bool = Body(..., embed=True)):
    if not _algo_engine:
        raise HTTPException(status_code=503, detail="AlgoEngine no inicializado")
    _algo_engine.set_live_mode(enabled)
    mode = "LIVE (órdenes automáticas)" if enabled else "SIGNAL_ONLY (solo señales)"
    return {"status": "updated", "live_mode": enabled, "message": f"Modo: {mode}"}
@router.get("/llama/status")
async def get_llama_status():
    return {
        "big": {
            "active": _big_llama_engine._active if _big_llama_engine else False,
            "config": _big_llama_engine._symbols_config if _big_llama_engine else {}
        },
        "inbalance": {
            "active": _inbalance_llama_engine._active if _inbalance_llama_engine else False,
            "config": _inbalance_llama_engine._symbols_config if _inbalance_llama_engine else {}
        },
        "caza": {
            "active": _caza_llama_engine._active if _caza_llama_engine else False,
            "config": _caza_llama_engine._symbols_config if _caza_llama_engine else {}
        }
    }
@router.post("/llama/toggle")
async def toggle_llama(request: LlamaToggleRequest):
    engine = None
    if request.type == "big": engine = _big_llama_engine
    elif request.type == "inbalance": engine = _inbalance_llama_engine
    elif request.type == "caza": engine = _caza_llama_engine
    if not engine:
        raise HTTPException(status_code=400, detail=f"Engine type '{request.type}' not found")
    engine.set_active(request.active)
    return {"status": "success", "type": request.type, "active": request.active}
@router.websocket("/ws/feed")
async def websocket_feed(websocket: WebSocket):
    try:
        await websocket.accept()
        register_connection()
        await asyncio.sleep(0.1) 
        event_queue = asyncio.Queue(maxsize=1000)
        mde = await ensure_market_data_engine()
        if not mde:
            await websocket.close(code=1011, reason="No se pudo inicializar MarketDataEngine")
            return
        async def message_sender():
            try:
                while True:
                    event_dict = await event_queue.get()
                    try:
                        await websocket.send_json(event_dict)
                    except:
                        break
                    finally:
                        event_queue.task_done()
            except asyncio.CancelledError:
                pass
        sender_task = asyncio.create_task(message_sender())
        async def heartbeat_sender():
            try:
                while True:
                    await asyncio.sleep(15)
                    await event_queue.put({"event_type": "HEARTBEAT", "timestamp": time.time(), "status": "ALIVE"})
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Heartbeat sender error: {e}")
        heartbeat_task = asyncio.create_task(heartbeat_sender())
        loop = asyncio.get_event_loop()
        _last_emit_times = {}  # (symbol, event_type) -> last_time
        _events_sent = {"count": 0}  # Debug counter
        
        def sync_callback(event):
            try:
                d = event.to_dict()
                event_ts = d.get("timestamp", 0)
                event_type = d.get("event_type", "")
                symbol = d.get("symbol", "unknown")
                
                if not event_ts or event_ts <= 0:
                    return
                    
                now = time.time()
                
                # Throttle BOOK and QUOTE events to 40Hz (25ms) per symbol for fluidity
                # Throttle TICK events to 10Hz (100ms) — balanced between fluidity and bandwidth
                if event_type in ("BOOK", "QUOTE", "BOOK_UPDATE", "TICK"):
                    key = (symbol, event_type)
                    last_time = _last_emit_times.get(key, 0)
                    throttle_ms = 100 if event_type == "TICK" else 25  # 10Hz for TICK, 40Hz for others
                    if now - last_time < (throttle_ms / 1000):
                        return
                    _last_emit_times[key] = now

                # Filters de tiempo estrictos — igual que versión FUNCIONAL estable
                if event_ts > now + 5: # Máximo 5s en el futuro
                    return
                age_s = now - event_ts
                if event_type == "TRADE" and age_s > 60: # Trades de más de 60s
                    return  
                if event_type in ("QUOTE", "OHLCV", "BOOK", "TICK", "BAR") and age_s > 300:
                    return
                if event_type not in ("TRADE", "QUOTE", "OHLCV", "BOOK", "TICK", "BAR", "HEARTBEAT", "LLAMA_UPDATE") and age_s > 60:
                    return  
                
                loop.call_soon_threadsafe(
                    lambda: event_queue.put_nowait(d) if not event_queue.full() else None
                )
                _events_sent["count"] += 1
                
                # Debug log every 100 events
                if _events_sent["count"] % 100 == 0:
                    logger.info(f"[WS_FEED] Sent {_events_sent['count']} events, last: {event_type} {symbol}")
            except:
                pass

        _market_data_engine.subscribe_to_events(sync_callback)
        _llama_callbacks = []  
        def create_llama_callback(llama_type):
            def callback(symbol, params):
                try:
                    loop.call_soon_threadsafe(
                        lambda: event_queue.put_nowait({
                            "event_type": "LLAMA_UPDATE",
                            "llama_type": llama_type,
                            "symbol": symbol,
                            "params": params,
                            "timestamp": time.time()
                        }) if not event_queue.full() else None
                    )
                except:
                    pass
            return callback
        if _big_llama_engine:
            cb = create_llama_callback("big")
            _big_llama_engine.subscribe_to_updates(cb)
            _llama_callbacks.append((_big_llama_engine, cb))
        if _inbalance_llama_engine:
            cb = create_llama_callback("inbalance")
            _inbalance_llama_engine.subscribe_to_updates(cb)
            _llama_callbacks.append((_inbalance_llama_engine, cb))
        if _caza_llama_engine:
            cb = create_llama_callback("caza")
            _caza_llama_engine.subscribe_to_updates(cb)
            _llama_callbacks.append((_caza_llama_engine, cb))
        try:
            while True:
                message = await websocket.receive_text()
                try:
                    cmd = json.loads(message)
                    if cmd.get("action") == "subscribe":
                        symbols = cmd.get("symbols", [])
                        logger.info(f"[WS_FEED] Client subscribing to: {symbols}")
                        _market_data_engine.subscribe(symbols)
                        event_queue.put_nowait({"status": "subscribed", "symbols": symbols})
                    elif cmd.get("action") == "unsubscribe":
                        symbols = cmd.get("symbols", [])
                        _market_data_engine.unsubscribe(symbols)
                        event_queue.put_nowait({"status": "unsubscribed", "symbols": symbols})
                except Exception as e:
                    logger.error(f"Error procesando comando WS: {e}")
        except WebSocketDisconnect:
            pass
        finally:
            _market_data_engine.unsubscribe_from_events(sync_callback)
            for engine, cb in _llama_callbacks:
                try:
                    if hasattr(engine, '_update_callbacks') and cb in engine._update_callbacks:
                        engine._update_callbacks.remove(cb)
                except Exception:
                    pass
            sender_task.cancel()
            heartbeat_task.cancel()
    except Exception as e:
        logger.error(f"Error en WebSocket feed: {e}")
    finally:
        unregister_connection()
@router.websocket("/ws/orders")
async def websocket_orders(websocket: WebSocket):
    try:
        await websocket.accept()
        register_connection()  
        og = await ensure_order_gateway()
        if not og:
            await websocket.close(code=1011, reason="No se pudo inicializar OrderGateway")
            return
        async def send_response(response):
            try:
                await websocket.send_json(response.to_dict())
            except:
                pass
        def sync_callback(response):
            asyncio.create_task(send_response(response))
        _order_gateway.subscribe_to_orders(sync_callback)
        try:
            while True:
                await websocket.receive_text()  
        except WebSocketDisconnect:
            pass
        finally:
            _order_gateway.unsubscribe_from_orders(sync_callback)
    except Exception as e:
        print(f"WS Orders Error: {e}")
    finally:
        unregister_connection()  
@router.websocket("/ws/algo")
async def websocket_algo(websocket: WebSocket):
    try:
        await websocket.accept()
        register_connection()  
        ae = await ensure_algo_engine()
        if not ae:
            await websocket.close(code=1011, reason="No se pudo inicializar AlgoEngine")
            return
        async def send_signal(signal, confidence, metadata):
            try:
                await websocket.send_json(
                    {
                        "type": "signal",
                        "signal": signal,
                        "confidence": confidence,
                        "metadata": metadata,
                        "timestamp": time.time(),
                    }
                )
            except:
                pass
        def sync_callback(signal, confidence, metadata):
            asyncio.create_task(send_signal(signal, confidence, metadata))
        _algo_engine.subscribe_to_signals(sync_callback)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            _algo_engine.unsubscribe_from_signals(sync_callback)
    except Exception as e:
        print(f"WS Algo Error: {e}")
    finally:
        unregister_connection()  
async def startup_services(platform: str = "mt5"):
    global _market_data_engine, _order_gateway, _algo_engine, _big_llama_engine
    global _market_data_engine, _order_gateway, _algo_engine, _big_llama_engine, _inbalance_llama_engine, _caza_llama_engine
    from src.services.algo_engine import AlgoEngine
    from src.services.market_data_engine import MarketDataEngine
    from src.services.mt5_launcher import get_launcher
    from src.services.order_gateway import OrderGateway
    from src.services.big_llama.engine import BigLlamaEngine, InbalanceLlamaEngine, CazaLlamaEngine
    _market_data_engine = MarketDataEngine(platform=platform)
    _order_gateway = OrderGateway(platform=platform)
    _algo_engine = AlgoEngine()
    _big_llama_engine = BigLlamaEngine()
    _inbalance_llama_engine = InbalanceLlamaEngine()
    _caza_llama_engine = CazaLlamaEngine()
    _order_gateway.set_market_data_engine(_market_data_engine)
    _algo_engine.set_market_data_engine(_market_data_engine)
    _algo_engine.set_order_gateway(_order_gateway)
    _big_llama_engine.set_market_data_engine(_market_data_engine)
    _inbalance_llama_engine.set_market_data_engine(_market_data_engine)
    _caza_llama_engine.set_market_data_engine(_market_data_engine)
    init_services(_market_data_engine, _order_gateway, _algo_engine, _big_llama_engine, _inbalance_llama_engine, _caza_llama_engine)
    async def _init_background():
        print("INFO: Iniciando procesos de fondo en 0.5s...")
        await asyncio.sleep(0.5)
        try:
            # Quitamos el autolanzamiento de MT5 aquí. El usuario puede abrirlo por su cuenta o ya tenerlo abierto.
            # Solo iniciamos el ciclo de conexión del market_data_engine que intentará conectarse a la terminal activa de MT5 si la encuentra,
            # pero no la forzará a abrir bloqueando la experiencia o forzando su uso (importante para usuarios que operan full Crypto).
            
            print("INFO: Conectando motor de mercado al broker actual...")
            loop = asyncio.get_event_loop()
            success_mde = await loop.run_in_executor(None, _market_data_engine.start)
            if success_mde:
                _order_gateway.start()
                print("INFO: Conexión establecida y servicios operativos.")
            else:
                print(
                    "WARNING: Motor de mercado no pudo conectar inicialmente. Reintentando en bucle interno."
                )
        except Exception as e:
            print(f"ERROR CRÍTICO en la inicialización de fondo: {e}")
            import traceback
            traceback.print_exc()
    asyncio.create_task(_init_background())
    asyncio.create_task(_safety_timeout_task())
    return {
        "status": "starting_async",
        "detail": "MT5 and Engines are launching in background",
    }
@router.get("/config")
async def get_config():
    from src.services.database import get_settings
    settings = get_settings()
    if "extra_settings" in settings and isinstance(settings["extra_settings"], str):
        try:
            extra = json.loads(settings["extra_settings"])
            settings.update(extra)
        except:
            pass
        del settings["extra_settings"]  
    return settings
@router.post("/config")
async def save_config(config: Dict[str, Any] = Body(...)):
    from src.services.database import save_settings
    known_columns = {
        "platform",
        "theme",
        "show_grid",
        "show_watermark",
        "one_click_trading",
        "timer_enabled",
        "timer_position",
        "timer_size",
        "timer_color",
        "timer_show_progress",
        "last_active_workspace",
    }
    main_data = {}
    extra_data = {}
    for k, v in config.items():
        if k in known_columns:
            main_data[k] = v
        else:
            extra_data[k] = v
    if extra_data:
        main_data["extra_settings"] = json.dumps(extra_data)
    if save_settings(main_data):
        return {"status": "saved"}
    raise HTTPException(status_code=500, detail="Error saving settings")
@router.post("/system/shutdown")
async def trigger_shutdown():
    print("SHUTDOWN: Solicitud de apagado recibida desde UI.")
    async def _kill_soon():
        await asyncio.sleep(1)
        await shutdown_services()
        print("SHUTDOWN: Ejecutando salida forzada del proceso Python.")
        import os
        os._exit(0)
    asyncio.create_task(_kill_soon())
    return {"status": "shutting_down", "message": "Sistema apagándose en 1 segundo..."}
async def shutdown_services():
    global _market_data_engine, _order_gateway, _algo_engine
    print("INFO: Deteniendo servicios de la plataforma...")
    async def _do_shutdown():
        if _algo_engine:
            try:
                _algo_engine.stop()
            except:
                pass
        if _order_gateway:
            try:
                _order_gateway.stop()
            except:
                pass
        if _market_data_engine:
            try:
                _market_data_engine.stop()
            except:
                pass
        if _big_llama_engine: _big_llama_engine.stop()
        if _inbalance_llama_engine: _inbalance_llama_engine.stop()
        if _caza_llama_engine: _caza_llama_engine.stop()
        try:
            from src.services.mt5_launcher import get_launcher
            launcher = get_launcher()
            launcher.stop_hiding_loop()
            launcher.stop()
            print("INFO: MT5 detenido correctamente.")
        except Exception as e:
            print(f"WARNING: Error deteniendo MT5 Launcher: {e}")
    try:
        await asyncio.wait_for(_do_shutdown(), timeout=5.0)
    except asyncio.TimeoutError:
        print("WARNING: Timeout detectado en el apagado. Forzando salida...")
    except Exception as e:
        print(f"ERROR durante el apagado: {e}")