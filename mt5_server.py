from fastapi import FastAPI, HTTPException, Request
from starlette.middleware.gzip import GZipMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Union
import uvicorn
import pandas as pd
import json

from src.live.mt5_native_connector import MT5Connector
from src.live.mt5_bridge_auth import bridge_bind, require_bridge_token
from src.live.mt5_bridge_session import ensure_connected
from src.live.mt5_terminal_demand import (
    TerminalDemand,
    allow_terminal_boot,
    terminal_process_running,
)

app = FastAPI(title="MT5 Wine Server", version="1.0.0")
# The symbol catalogue is ~1 MB of repetitive JSON; compress it for slow tunnels.
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.middleware("http")(require_bridge_token)
connector = MT5Connector()

#: Authorises the ONE action that opens a terminal window: ``mt5.initialize()``
#: boots ``terminal64.exe`` when nothing answers, so background polling must not
#: reach it. Renewed by connected browser sessions only.
terminal_demand = TerminalDemand()

_SESSION_EXEMPT_PATHS = {
    "/api/shutdown",
    "/docs",
    "/openapi.json",
    # Peer routes must answer immediately (the platform sets the lease BEFORE it
    # starts polling) and must never boot the terminal themselves.
    "/api/terminal/demand",
    "/api/terminal/status",
}


@app.middleware("http")
async def ensure_mt5_session(request: Request, call_next):
    """Reconnect the shared MT5 session, but only where a boot is authorised."""
    if request.url.path not in _SESSION_EXEMPT_PATHS:
        if allow_terminal_boot(connector, terminal_demand):
            ensure_connected(connector)
    return await call_next(request)


class DemandRequest(BaseModel):
    """Optional sequence and sender so out-of-order deliveries cannot flip the lease.

    The sequence is scoped per sender: several platforms can drive one bridge, and
    their counters are independent.
    """

    seq: Optional[int] = None
    sender: Optional[str] = None


@app.post("/api/terminal/demand")
def api_terminal_demand(payload: Optional[DemandRequest] = None):
    """A platform session is open: allow the terminal to be booted."""
    remaining = terminal_demand.renew(
        payload.seq if payload else None, payload.sender if payload else None
    )
    if remaining is None:
        return {"active": terminal_demand.active(), "applied": False}
    return {"active": True, "expires_in": remaining, "applied": True}


@app.delete("/api/terminal/demand")
def api_terminal_demand_release(payload: Optional[DemandRequest] = None):
    """The last platform session closed: stop authorising a boot right away.

    Revoking here matters because the lease would otherwise stay valid for
    ``MT5_TERMINAL_DEMAND_TTL`` after the window closed, and a single background
    poll inside that window boots a terminal for nobody. Nothing is terminated.
    """
    applied = terminal_demand.revoke(
        payload.seq if payload else None, payload.sender if payload else None
    )
    return {"active": terminal_demand.active(), "applied": applied}


@app.get("/api/terminal/status")
def api_terminal_status():
    """Why the terminal is or is not being served, without booting anything."""
    try:
        session_alive = bool(connector.is_alive())
    except Exception:
        session_alive = False
    return {
        "terminal_running": terminal_process_running(),
        "session_alive": session_alive,
        "demand_active": terminal_demand.active(),
        "demand_remaining_seconds": terminal_demand.remaining(),
    }

class ConnectRequest(BaseModel):
    path: Optional[str] = None

class OrderRequestModel(BaseModel):
    symbol: str
    order_type: Optional[str] = None
    volume: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    price: Optional[float] = None
    mode: str = "MKT"
    side: Optional[str] = None
    amount: Optional[float] = None

@app.post("/api/connect")
def api_connect(req: ConnectRequest):
    success = connector.connect(req.path)
    return {"success": success}

@app.post("/api/shutdown")
def api_shutdown():
    connector.shutdown()
    return {"success": True}

@app.get("/api/balance")
def api_balance():
    return {"balance": connector.get_balance()}

@app.get("/api/account_info")
def api_account_info():
    info = connector.get_account_info()
    if info is None:
        raise HTTPException(status_code=500, detail="Not connected or info missing")
    return info

@app.get("/api/current_price/{symbol}")
def api_current_price(symbol: str):
    price = connector.get_current_price(symbol)
    if price is None:
        raise HTTPException(status_code=404, detail="Symbol not found or disconnected")
    return {"price": price}

@app.get("/api/latest_candles/{symbol}")
def api_latest_candles(symbol: str, timeframe: str = "1m", n: int = 100):
    df = connector.get_latest_candles(symbol, timeframe, n)
    if df is None:
        raise HTTPException(status_code=500, detail="Failed to get candles")
    # Asegurarnos de que el tiempo se exporte correctamente a string
    if 'time' in df.columns:
        df['time'] = df['time'].astype(str)
    return df.to_dict(orient="records")

@app.get("/api/deals")
def api_deals(date_from: Optional[str] = None, date_to: Optional[str] = None):
    dt_from = pd.to_datetime(date_from) if date_from else None
    dt_to = pd.to_datetime(date_to) if date_to else None
    deals = connector.get_deals(date_from=dt_from, date_to=dt_to)
    return [d._asdict() if hasattr(d, "_asdict") else dict(d) for d in deals]


@app.get("/api/positions")
def api_positions(symbol: Optional[str] = None, ticket: Optional[str] = None):
    pos = connector.get_positions(symbol, ticket)
    return [p._asdict() if hasattr(p, "_asdict") else dict(p) for p in pos]

@app.get("/api/pending_orders")
def api_pending_orders(symbol: Optional[str] = None):
    return connector.get_pending_orders(symbol)

@app.post("/api/place_order")
def api_place_order(req: OrderRequestModel):
    res = connector.place_order(
        symbol=req.symbol,
        order_type=req.order_type,
        volume=req.volume,
        sl=req.sl,
        tp=req.tp,
        price=req.price,
        mode=req.mode,
        side=req.side,
        amount=req.amount
    )
    if res is None:
        raise HTTPException(status_code=500, detail="Order failed completely")
    return res._asdict() if hasattr(res, "_asdict") else res

@app.post("/api/close_position/{ticket}")
def api_close_position(ticket: int, symbol: Optional[str] = None, volume: Optional[float] = None):
    res = connector.close_position(ticket, symbol, volume)
    if not res:
        raise HTTPException(status_code=500, detail="Failed to close position")
    return res._asdict() if hasattr(res, "_asdict") else res

class ModifyPositionRequest(BaseModel):
    sl: Optional[float] = None
    tp: Optional[float] = None
    symbol: Optional[str] = None

@app.post("/api/modify_position/{ticket}")
def api_modify_position(ticket: int, req: ModifyPositionRequest):
    res = connector.modify_position(ticket, req.sl, req.tp, req.symbol)
    if not res:
        raise HTTPException(status_code=500, detail="Failed to modify position")
    return res._asdict() if hasattr(res, "_asdict") else res

class ModifyOrderRequest(BaseModel):
    price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None

@app.post("/api/modify_order/{ticket}")
def api_modify_order(ticket: int, req: ModifyOrderRequest):
    res = connector.modify_order(ticket, req.price, req.sl, req.tp)
    if not res:
        raise HTTPException(status_code=500, detail="Failed to modify order")
    return res._asdict() if hasattr(res, "_asdict") else res

@app.get("/api/daily_pnl")
def api_daily_pnl():
    return {"pnl": connector.get_daily_pnl()}

@app.get("/api/recent_ticks/{symbol}")
def api_recent_ticks(symbol: str, n: int = 1000):
    df = connector.get_recent_ticks(symbol, n)
    if df is None:
        return []
    return df.to_dict(orient="records")

@app.get("/api/ticks_since/{symbol}")
def api_ticks_since(symbol: str, from_msc: float):
    df = connector.get_ticks_since(symbol, from_msc)
    if df is None:
        return []
    return df.to_dict(orient="records")

@app.get("/api/book_snapshot/{symbol}")
def api_book_snapshot(symbol: str, limit: int = 100):
    book = connector.get_book_snapshot(symbol, limit)
    return book

@app.get("/api/symbols")
def api_symbols(group: Optional[str] = None, pattern: Optional[str] = None):
    return connector.symbols_get(group=group, pattern=pattern)

@app.get("/api/symbol_info/{symbol}")
def api_symbol_info(symbol: str):
    info = connector.symbol_info(symbol)
    if info is None: return None
    # Convertir objeto a dict
    return {slot: getattr(info, slot) for slot in info.__slots__} if hasattr(info, '__slots__') else dict(info._asdict()) if hasattr(info, '_asdict') else info

@app.post("/api/symbol_select")
def api_symbol_select(data: dict):
    return {"success": connector.symbol_select(data.get("symbol"), data.get("enable", True))}

@app.get("/api/copy_rates_from_pos/{symbol}")
def api_copy_rates_from_pos(symbol: str, timeframe: int, start_pos: int, count: int):
    rates = connector.copy_rates_from_pos(symbol, timeframe, start_pos, count)
    if rates is None: return []
    return pd.DataFrame(rates).to_dict(orient="records")

@app.get("/api/copy_ticks_range/{symbol}")
def api_copy_ticks_range(symbol: str, date_from: float, date_to: float, flags: int):
    from datetime import datetime
    dt_from = datetime.fromtimestamp(date_from)
    dt_to = datetime.fromtimestamp(date_to)
    ticks = connector.copy_ticks_range(symbol, dt_from, dt_to, flags)
    if ticks is None: return []
    return pd.DataFrame(ticks).to_dict(orient="records")

@app.get("/api/symbol_details/{symbol}")
def api_symbol_details(symbol: str):
    return connector.get_symbol_details(symbol)

if __name__ == "__main__":
    host, port = bridge_bind()
    uvicorn.run(app, host=host, port=port)
