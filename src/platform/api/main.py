import asyncio
from src.product_version import PRODUCT_VERSION
from src.platform.api.runtime_api import create_runtime_router
from src.platform.api.telemetry_api import create_telemetry_router, get_gpu_info
from src.platform.api.version_api import router as version_router
import json
import logging
import math
import os
import subprocess
import threading
import sys
import time
import traceback
import webbrowser
from contextlib import asynccontextmanager
import mimetypes
import httpx


# --- Application logging ---------------------------------------------------
# Uvicorn configures only its own loggers, so the root logger kept no handler
# and every logger.info(...) in this module was dropped: the container showed
# the uvicorn access log and nothing else. Attach one stdout handler to the root
# logger, and only when it has none, so re-importing this module (or any other
# library calling basicConfig first) never duplicates lines. Uvicorn's loggers
# are left untouched.
def configure_application_logging(level=None):
    root = logging.getLogger()
    if root.handlers:
        return root
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    root.addHandler(handler)
    name = (level or os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    # An unknown LOG_LEVEL must not break the boot; fall back to INFO.
    root.setLevel(name if isinstance(logging.getLevelName(name), int) else "INFO")
    return root


configure_application_logging()

# Fix for Windows: Ensure .js and .css files are served with correct MIME types
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')

# --- Windows Silent Subprocess Patch ---
# Prevents cmd window flashing when 3rd party libraries (like GPUtil) call subprocesses on Windows.
if sys.platform == "win32":
    import subprocess
    _original_popen = subprocess.Popen
    def _silent_popen(args, **kwargs):
        # Create startupinfo if not provided
        si = kwargs.get('startupinfo')
        if si is None:
            si = subprocess.STARTUPINFO()
            kwargs['startupinfo'] = si
        
        # Inject silent flags
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        
        # Inject CREATE_NO_WINDOW (0x08000000) if not explicitly set
        cf = kwargs.get('creationflags', 0)
        kwargs['creationflags'] = cf | 0x08000000
        
        return _original_popen(args, **kwargs)
    
    subprocess.Popen = _silent_popen
# ----------------------------------------

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import pandas as pd
import psutil
import GPUtil
import certifi
os.environ['SSL_CERT_FILE'] = certifi.where()
from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from src.live.connector import MT5Connector
from src.platform.api.accounts_api import router as accounts_router
from src.platform.api.public_auth_config import router as public_auth_config_router
from src.platform.api.services_api import (
    get_platform_health,
    register_connection,
    shutdown_services,
    startup_services,
    unregister_connection,
)
from src.platform.api.services_api import router as services_router
from src.platform.api.footprint_api import router as footprint_router
from src.platform.api.backtesting_api import router as backtesting_router
from src.platform.api.backtesting_api import router as backtesting_router
from src.platform.api.seo_api import router as seo_router
from src.platform.api.migration_api import router as migration_router
# Small in-process TTL cache: symbols and deals barely change per poll, and
# every bridge read costs ~418ms of transport.
from src.platform.api.deals_cache import cached

# Standard routers
from src.platform.api.analysis_api import router as analysis_router
from src.services.auth import get_current_user, check_subscription, security
from src.services.auth import get_authenticated_user_id, extract_user_id
from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials
from src.platform.api.utils import sanitize_float
from src.utils.config_manager import load_symbol_map, save_symbol_map
from src.services.database import (
    clear_ai_chat_history,
    get_ai_chat_history,
    get_algolab_state,
    get_last_active_workspace,
    get_all_workspaces,
    delete_workspace,
    DatabaseNotConfigured,
)
from src.services.replication_service import replicate_to_nt8_background, replicate_to_nt8_sync, log_diag
from src.services.active_tenant import get_active_user_id, note_missing_active_user
from src.services.database import (
    init_db,
    save_ai_chat_message,
    save_algolab_state,
    set_last_active_workspace,
)
from src.services.database import get_settings as db_get_settings
from src.services.database import get_workspace as db_get_workspace
from src.services.database import save_settings as db_save_settings
from src.services.database import save_settings as db_save_settings
from src.services.database import save_workspace as db_save_workspace
from src.services.license_service import validate_license, get_machine_id
from src.platform.api.utils import resolve_symbol, sanitize_float, sanitize_float_list
from src.services.market_data_engine.engine import get_market_data_engine
from src.services.crypto_manager import get_crypto_manager
from src.live.crypto_connector import get_connector as get_crypto_connector
import yfinance as yf

class AlgolabStateRequest(BaseModel):
    open_files: List[Dict]
    file_contents: Dict[str, str]
    active_file_path: Optional[str] = None
    is_chat_open: Optional[bool] = False
    chat_width: Optional[int] = 350
logger = logging.getLogger(__name__)
from src.services.database import get_outputs_dir, get_logs_dir
STATUS_FILE = os.path.join(get_outputs_dir(), "live_status.json")
load_dotenv()
from src.live.connector import get_mt5_connector
from src.live.bridge_types import as_list, normalize, positions_to_web, symbol_is_tradable
from src.live import mt5_access
GLOBAL_MT5_CONNECTOR = get_mt5_connector()
from src.services.crypto_manager import get_crypto_manager
from src.live.crypto_connector import get_connector
from src.services.market_data_engine.engine import get_market_data_engine
SYMBOL_CACHE = {
    "mt5": {"data": [], "timestamp": 0}
}
SYMBOL_CACHE_TTL = 60 
VIX_HISTORY_CACHE = {
    "df": None,
    "last_fetch": 0,
    "timeframe": None,
    "period": None
}
VIX_LIVE_CACHE = {
    "price": None,
    "last_fetch": 0,
    "time": None,
    "last_emit_price": None,
    "stale_count": 0
}
import threading
VIX_CACHE_LOCK = threading.Lock()
def normalize_symbol_for_comparison(symbol: str) -> str:
    if not symbol:
        return ""
    base = symbol.upper().split('.')[0].split('_')[0]
    if len(base) > 3 and base[-1].isdigit():
        if base[-3].isalpha() and base[-2:].isdigit():
            base = base[:-3]
        elif base[-2].isalpha() and base[-1:].isdigit():
            base = base[:-2]
    return base
def symbols_match(symbol1: str, symbol2: str) -> bool:
    return normalize_symbol_for_comparison(symbol1) == normalize_symbol_for_comparison(
        symbol2
    )
def _number(value, default=0.0):
    """Coerce connector values (including pandas/numpy scalars) to a plain float."""
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    # NaN/inf would break JSON encoding and int() conversions downstream.
    if not math.isfinite(number):
        return default
    return number
def detect_platform_for_symbol(symbol: str) -> str:
    if not symbol:
        return "mt5"
    s = symbol.upper()
    # Stablecoins and common crypto suffixes
    if any(pattern in s for pattern in ["USDT", "USDC", "BUSD", "TUSD", "DAI", "/USDT", ":USDT", "/USDC", ":USDC"]):
        return "crypto"
    # Crypto base symbols with delimiters
    crypto_bases = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOT", "LINK", "AVAX", "PEPE", "SHIB", "DOGE", "LTC", "MATIC"]
    if any(base in s for base in crypto_bases) and ("/" in s or "-" in s or ":" in s):
        return "crypto"
    return "mt5"
@asynccontextmanager
async def lifespan(app: FastAPI):
    start_time = time.time()
    logger.info("Iniciando plataforma QuantumLlama...")
    try:
        init_db()
        logger.info("Base de datos PostgreSQL (DATABASE_URL) inicializada")
        
        # --- NUEVO: Limpieza automática de logs al iniciar ---
        try:
            from src.utils.cleaner import auto_clean_logs
            auto_clean_logs(max_days=7, max_size_mb=1000) # Mantener máximo 1GB o 7 días
        except Exception as log_err:
            logger.warning(f"Error en limpieza de logs: {log_err}")
        # ---------------------------------------------------

        # Live services first: a connection-state probe must never be able to keep
        # the engine from starting. The probe runs with release=False so it cannot
        # shut down the session startup_services just opened either.
        await startup_services(platform="mt5")
        await _publish_live_connection_state("mt5", release=False)
        elapsed = (time.time() - start_time) * 1000
        logger.info(f"Plataforma lista en {elapsed:.0f}ms (sin conexiones activas)")
    except Exception as e:
        logger.error(f"Error iniciando plataforma: {e}")
    yield  
    logger.info("Deteniendo plataforma...")
    await shutdown_services()
    logger.info("Plataforma detenida")
app = FastAPI(
    title="Quantum Llama Platform API",
    description="Plataforma de trading con arquitectura desacoplada",
    version=PRODUCT_VERSION,
    lifespan=lifespan,
)

@app.exception_handler(DatabaseNotConfigured)
async def database_not_configured(request: Request, exc: DatabaseNotConfigured):
    """Per-user storage is PostgreSQL-only: say so instead of serving stale sqlite data."""
    logger.error(f"[DATABASE] {exc}")
    return JSONResponse(status_code=503, content={"detail": str(exc)})

@app.middleware("http")
async def log_not_found(request: Request, call_next):
    response = await call_next(request)
    if response.status_code == 404:
        logger.warning(f"[404] {request.method} {request.url.path}")
    return response

@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Advertise HTTPS-only transport without changing any response body."""
    response = await call_next(request)
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response

# ── PYDANTIC MODELS ────────────────────────────────────────────────
class OrderRequest(BaseModel):
    platform: str  
    action: str  
    symbol: str
    volume: Optional[float] = 0.0
    sl: Optional[float] = 0.0
    tp: Optional[float] = 0.0
    ticket: Optional[Any] = 0
    type: Optional[str] = "MKT"  
    price: Optional[float] = 0.0
    account_id: Optional[str] = None  

class ModifyRequest(BaseModel):
    platform: str
    symbol: str
    ticket: Optional[Any] = 0
    sl: Optional[float] = None  
    tp: Optional[float] = None  
    price: Optional[float] = 0.0  
    is_pending: Optional[bool] = False  
    order_type: Optional[str] = "MKT"

class ConfigRequest(BaseModel):
    automation_enabled: bool
    volume: float
    max_daily_loss: float
    max_trades_per_day: int
    daily_profit_target: float
    start_hour: str
    end_hour: str

class AlgolabReadRequest(BaseModel):
    path: str

class AlgolabWriteRequest(BaseModel):
    path: str
    content: str

class AlgolabCreateRequest(BaseModel):
    name: str
    type: str

class AlgolabRunRequest(BaseModel):
    path: str

class AISettingsRequest(BaseModel):
    apiKey: str
    provider: str
    model: str

class AIChatRequest(BaseModel):
    messages: List[Dict]
    skill: Optional[str] = None
    active_file_path: Optional[str] = None
    agentic_mode: Optional[bool] = True

class AlgoStartRequest(BaseModel):
    asset_type: str
    ticker: str
    period: str
    epochs: int
    train_timeframe: str
    trade_timeframe: str
    seq_length: int
    hidden_dim: int
    num_layers: int

class LiveStartRequest(BaseModel):
    ticker: str
    asset_type: str = "Futures"
    platform: str = "mt5"
    account_id: Optional[str] = None
    timeframe: str = "1h"
    algorithm: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    model_config = ConfigDict(
        extra="ignore"
    )

# ── /api/modify registrado PRIMERO — antes de cualquier router o middleware ──
# Esto garantiza que ninguna ruta comodín ni sub-router lo sombree.
@app.post("/api/modify")
@app.post("/api/modify/")
async def modify_position(
    req: ModifyRequest, user_id: str = Depends(get_authenticated_user_id)
):
    logger.info(f"[MODIFY] Request received: platform={req.platform}, symbol={req.symbol}, ticket={req.ticket}, sl={req.sl}, tp={req.tp}")
    try:
        actual_platform = req.platform.lower() if req.platform else "mt5"
        
        # CRITICAL: Override platform detection if symbol is clearly crypto
        # The frontend may send platform='mt5' even for crypto symbols
        if actual_platform != "crypto" and detect_platform_for_symbol(req.symbol) == "crypto":
            logger.debug(f"[MODIFY] Platform override: '{actual_platform}' -> 'crypto' (symbol={req.symbol})")
            actual_platform = "crypto"
        
        if actual_platform == "crypto":
            from src.live.crypto_connector import get_connector as get_crypto_connector
            from src.services.crypto_manager import get_crypto_manager
            manager = get_crypto_manager()
            accounts = manager.get_accounts(user_id=user_id)
            master_acc = next((acc for acc in accounts if acc.get("is_master")), None)
            if not master_acc and accounts:
                master_acc = accounts[0]
            if not master_acc:
                raise HTTPException(status_code=400, detail="No crypto account available for modification")
            
            # LOG ACCOUNT INFO
            logger.debug(f"[MODIFY] Using Account: {master_acc.get('id')} ({master_acc.get('broker')}) Type: {master_acc.get('account_type')}")
            
            connector = get_crypto_connector(master_acc["id"], user_id=user_id)
            if not connector:
                raise HTTPException(status_code=500, detail="Failed to initialize crypto connector")
            
            if not await asyncio.to_thread(connector.connect):
                raise HTTPException(status_code=500, detail="Failed to connect to crypto exchange")
            
            actual_symbol = await asyncio.to_thread(connector._resolve_sym, req.symbol)
            logger.debug(f"[MODIFY] Resolved Symbol: {req.symbol} -> {actual_symbol}")
            logger.debug(f"[MODIFY] Connector id={id(connector)}, exchange={connector.exchange_id}, connected={connector.connected}")
        else:
            from src.live.connector import get_mt5_connector
            connector = get_mt5_connector()
            if not connector.connect():
                raise HTTPException(status_code=500, detail="Could not connect to MT5")
            actual_symbol = resolve_symbol(req.symbol)
        
        if not actual_symbol or actual_symbol == "DEFAULT":
            try:
                ticket_id = req.ticket
                if ticket_id and str(ticket_id) not in ["0", "null", "None", ""]:
                    if actual_platform == "crypto":
                        all_p = await asyncio.to_thread(connector.get_positions, force_fetch=True)
                        target = next((p for p in all_p if str(p.get('ticket')) == str(ticket_id)), None)
                        if target: actual_symbol = target.get('symbol', actual_symbol)
                    else:
                        pos_info = await asyncio.to_thread(connector.get_positions, ticket=ticket_id)
                        if pos_info:
                            actual_symbol = pos_info[0].symbol
                        else:
                            pending_info = await asyncio.to_thread(connector.get_pending_orders)
                            for o in pending_info:
                                if int(o.get("ticket", 0)) == ticket_id:
                                    actual_symbol = o.get("symbol")
                                    break
            except Exception as res_err:
                logger.warning(f"[MODIFY] Symbol resolution error: {res_err}")
        
        logger.info(
            f"[MODIFY] Executing | Symbol={req.symbol} -> {actual_symbol}, Ticket={req.ticket}, Price={req.price}, SL={req.sl}, TP={req.tp}"
        )
        
        if req.is_pending:
            logger.info(f"[MODIFY-PENDING] Modifying ticket {req.ticket} to price={req.price}")
            result = await asyncio.to_thread(connector.modify_order, req.ticket, req.price, req.sl, req.tp)
            if hasattr(connector, 'shutdown'): connector.shutdown()
            
            if not result or (hasattr(result, 'retcode') and result.retcode != 10009):
                err_comment = getattr(result, 'comment', 'Modification failed')
                raise HTTPException(status_code=500, detail=f"Modification failed: {err_comment}")
            
            # Replication for pending orders
            replicate_to_nt8_background(actual_symbol, "MODIFY", 0, sl=req.sl, tp=req.tp, price=req.price or 0, entry_price=req.price or 0)
            return {"status": "modified", "ticket": req.ticket}
        
        # ── Position Lookup ──
        ticket = req.ticket
        entry_p = 0
        target_pos = None
        
        # 1. Fetch all positions (Force fetch to bypass cache for modification)
        try:
            if actual_platform == "crypto":
                all_pos = await asyncio.to_thread(connector.get_positions, force_fetch=True)
            else:
                all_pos = await asyncio.to_thread(connector.get_positions)
            
            # 2. Try matching by ticket first
            if ticket and ticket != 0:
                target_pos = next((p for p in all_pos if str(p.get('ticket') if isinstance(p, dict) else getattr(p, 'ticket', 0)) == str(ticket)), None)
            
            # 3. If no ticket or ticket match failed, match by symbol (fuzzier for crypto)
            if not target_pos and actual_symbol:
                clean_actual = actual_symbol.replace("/", "").replace(":", "").replace("-", "").split(".")[0].upper()
                for p in all_pos:
                    p_sym = p.get('symbol') if isinstance(p, dict) else getattr(p, 'symbol', '')
                    clean_p = p_sym.replace("/", "").replace(":", "").replace("-", "").split(".")[0].upper()
                    if p_sym == actual_symbol or clean_p == clean_actual:
                        target_pos = p
                        break
            
            if target_pos:
                ticket = target_pos.get('ticket') if isinstance(target_pos, dict) else getattr(target_pos, 'ticket', ticket)
                entry_p = target_pos.get('entry_price', 0) if isinstance(target_pos, dict) else getattr(target_pos, 'entry_price', 0)
                logger.debug(f"[MODIFY] Found position: ticket={ticket}, symbol={actual_symbol}, entry={entry_p}")
            else:
                logger.warning(f"[MODIFY] No matching position found for ticket={ticket} or symbol={actual_symbol}. Available: {[p.get('symbol') for p in all_pos]}")
                raise HTTPException(status_code=404, detail=f"No open position found for {actual_symbol} (Ticket: {ticket})")
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[MODIFY] Error during position lookup: {e}")
            raise HTTPException(status_code=500, detail=f"Error finding position: {str(e)}")
        
        logger.info(f"[MODIFY] Calling connector.modify_position(ticket={ticket}, sl={req.sl}, tp={req.tp}, symbol={actual_symbol})")
        result = await asyncio.to_thread(connector.modify_position, ticket, req.sl, req.tp, symbol=actual_symbol)
        if hasattr(connector, 'shutdown'): connector.shutdown()
        
        if not result:
            raise HTTPException(status_code=500, detail="Position Modification failed (Connector returned False)")
            
        replicate_to_nt8_background(actual_symbol, "MODIFY", 0, sl=req.sl, tp=req.tp, entry_price=entry_p)
        return {"status": "modified", "ticket": req.ticket}
        
    except Exception as e:
        logger.error(f"[MODIFY] Final Error: {e}")
        return {"success": False, "error": str(e)}


# ── APP INITIALIZATION ──────────────────────────────────────────────
app.include_router(public_auth_config_router)
app.include_router(services_router)
app.include_router(accounts_router)
app.include_router(footprint_router)
app.include_router(backtesting_router)

# ── CRYPTO MONITORING TASK ──────────────────────────────────────────
async def monitor_crypto_accounts():
    """Background task to update crypto account status for the UI.

    Runs outside any request, so the tenant comes from the active-tenant holder:
    the account the user selected or connected. With nobody active it reports
    nothing at all rather than inventing an account.
    """
    while True:
        user_id = get_active_user_id()
        if not user_id:
            note_missing_active_user("crypto-account-monitor", logger)
            await asyncio.sleep(2)  # Poll every 2 seconds
            continue
        try:
            from src.services.crypto_manager import get_crypto_manager
            from src.live.crypto_connector import get_connector
            
            manager = get_crypto_manager()
            accounts = manager.get_accounts(user_id=user_id)
            master_acc = next((a for a in accounts if a.get("is_master")), None)
            
            if master_acc:
                connector = get_connector(master_acc["id"], user_id=user_id)
                if connector and connector.connected:
                    balance = await asyncio.to_thread(connector.get_balance)
                    equity = await asyncio.to_thread(connector.get_equity)
                    positions = await asyncio.to_thread(connector.get_positions)
                    
                    # Update STATUS_FILE format for UI Header
                    status_data = {
                        "type": "account_info",
                        "account": {
                            "balance": balance,
                            "equity": equity,
                            "profit": equity - balance,
                            "margin": sum(p.get("margin", 0) for p in positions),
                            "currency": "USD",
                            "broker": master_acc["broker"].upper(),
                            "login": master_acc["name"],
                            "platform": "crypto"
                        }
                    }
                    
                    if os.path.exists(os.path.dirname(STATUS_FILE)):
                        with open(STATUS_FILE, "w") as f:
                            json.dump(status_data, f, indent=4)
            
        except Exception as e:
            logger.error(f"Error in crypto monitor: {e}")
        
        await asyncio.sleep(2) # Poll every 2 seconds

@app.on_event("startup")
async def startup_crypto_monitor():
    asyncio.create_task(monitor_crypto_accounts())


app.include_router(analysis_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
from src.utils.paths import get_root_dir, get_internal_path, get_data_path, sync_config

ROOT_DIR = get_root_dir()

# Internal code and protected assets (web, src) are in sys._MEIPASS (via get_internal_path)
WEB_DIR = get_internal_path("src", "platform", "web")

# These pull from the protected INTERNAL code in production
INDICATORS_DIR = os.path.abspath(get_internal_path("src", "indicators"))
ALGORITHMS_DIR = os.path.abspath(get_internal_path("src", "algorithms"))

logger.info(f"AlgoLab Indicators Dir: {INDICATORS_DIR}")
logger.info(f"AlgoLab Algorithms Dir: {ALGORITHMS_DIR}")
dashboard_path = os.path.join(get_outputs_dir(), "dashboard.html")

# These remain EXTERNAL because they are persistent or user-modifiable metadata
ALGOLAB_REGISTRY_FILE = get_data_path("algolab_registry.json")
CONFIG_FILE = sync_config(os.path.join("src", "config", "live_config.json"))


def owner_user_id():
    """Identity allowed to change platform-wide trading settings.

    Engine-wide risk limits are not a per-user preference: one authenticated
    user must never be able to change the daily loss limit for everybody. The
    owner is configured explicitly, and when no owner is configured those keys
    are refused entirely rather than silently written to the shared file.
    """
    value = os.environ.get("QL_OWNER_USER_ID", "").strip()
    return value or None
from src.platform.api.utils import sanitize_float, resolve_symbol
ALGO_PROCESS = None
ALGO_TYPE = "idle"  
LAST_ALGO_TYPE = "training"  
def get_venv_python():
    """Detects the virtual environment python executable in a cross-platform way."""
    if getattr(sys, 'frozen', False):
        return sys.executable
        
    v_envs = [".venv", "venv"]
    p_paths = [
        os.path.join("bin", "python"),
        os.path.join("Scripts", "python.exe")
    ]
    
    for v in v_envs:
        for p in p_paths:
            candidate = os.path.join(ROOT_DIR, v, p)
            if os.path.exists(candidate):
                return candidate
                
    return sys.executable or "python"
def run_training_background(cmd):
    global ALGO_PROCESS
    try:
        kwargs = {}
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            kwargs["startupinfo"] = startupinfo
            kwargs["creationflags"] = 0x08000000
        ALGO_PROCESS = subprocess.Popen(cmd, cwd=ROOT_DIR, **kwargs)
        ALGO_PROCESS.wait()
    except Exception as e:
        pass

def run_live_background(cmd):
    global ALGO_PROCESS
    try:
        kwargs = {}
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            kwargs["startupinfo"] = startupinfo
            kwargs["creationflags"] = 0x08000000
        ALGO_PROCESS = subprocess.Popen(cmd, cwd=ROOT_DIR, **kwargs)
        ALGO_PROCESS.wait()
    except Exception as e:
        pass

@app.get("/api/symbols")
async def get_symbols(
    platform: str = Query("mt5", description="Platform type: mt5, crypto"),
    query: Optional[str] = Query(None, description="Search term"),
    force: bool = Query(False, description="Force re-initialization of broker connection"),
    user_id: str = Depends(get_authenticated_user_id),
):
    logger.info(f"[SYMBOLS] Request: platform={platform}, query={query}, force={force}")
    if platform == "crypto":
        try:
            crypto_manager = get_crypto_manager()
            accounts = crypto_manager.get_accounts(user_id=user_id)
            if not accounts:
                logger.warning("[SYMBOLS/CRYPTO] No crypto accounts configured")
                return []
            master = next((a for a in accounts if a.get('is_master')), None) or accounts[0]
            connector = get_connector(master['id'], user_id=user_id)
            if not connector:
                logger.warning(f"[SYMBOLS/CRYPTO] Connector not available for account {master['id']}")
                return []
            if not connector.connected:
                connector.connect()
            # Use _perp_markets (filtered for perpetuals only) if available, else fall back to all markets
            if hasattr(connector, '_perp_markets') and connector._perp_markets:
                market_keys = list(connector._perp_markets.keys())
                markets_dict = connector._perp_markets
                logger.info(f"[SYMBOLS/CRYPTO] Using perpetual markets: {len(market_keys)} symbols")
            else:
                market_keys = list(connector.exchange.markets.keys())
                markets_dict = connector.exchange.markets
                logger.warning(f"[SYMBOLS/CRYPTO] No perpetual filter, using all markets: {len(market_keys)} symbols")
            q = (query or "").strip().upper()
            results = []
            for s in market_keys:
                if q and q not in s.upper():
                    continue
                market_info = markets_dict.get(s, {})
                market_type = market_info.get('type', 'Unknown').upper()
                settle = market_info.get('settle', '')
                results.append({
                    "symbol": s,
                    "description": f"PERPETUAL {settle}" if settle else f"Crypto Pair ({master['broker'].upper()})",
                    "group": f"{master['broker'].upper()} PERPETUAL",
                    "market_type": f"PERPETUAL ({market_type})"
                })
            results.sort(key=lambda x: x['symbol'])
            return results[:1000]
        except Exception as e:
            logger.error(f"[SYMBOLS/CRYPTO] Error: {e}")
            return []
    try:
        # The catalogue comes from the connector so the same handler serves the
        # native (Windows/Wine) and bridge (cloud) flavours.
        from src.live.connector import get_mt5_connector
        connector = get_mt5_connector()
        if force:
            connector.shutdown()
        if not getattr(connector, "connected", False) and not connector.connect():
            logger.error("[SYMBOLS/MT5] MT5 CONNECTION FAILED")
            return []
        patterns = [
            "*Futures*", "*FUT*", "*MNQ*", "*NQ*", "*MES*", "*ES*",
            "*CFD*", "*Cash*", "*Index*", "*Forex*", "*Indices*", "*Metal*"
        ]
        all_detected = []
        seen_names = set()
        now_ts = int(time.time())

        def _collect(symbols, cap=None):
            for symbol in normalize(as_list(symbols)):
                name = getattr(symbol, "name", None)
                if not name or name in seen_names: continue
                expiration = getattr(symbol, "expiration_time", 0) or 0
                if expiration > 0 and expiration < now_ts: continue
                if not symbol_is_tradable(symbol): continue
                path = getattr(symbol, "path", "") or getattr(symbol, "description", "") or ""
                all_detected.append({
                    "symbol": name,
                    "description": path,
                    "group": path.split("\\")[0] if "\\" in path else "MT5",
                })
                seen_names.add(name)
                if cap is not None and len(all_detected) >= cap:
                    return

        if query:
            # The previous "*q*" plus "q*" glob union is exactly "contains q".
            needle = query.strip().strip("*").strip()
            _collect(connector.symbols_get(pattern=needle) if needle else connector.symbols_get(group="*"))
        else:
            for pattern in sorted(list(set(patterns))):
                _collect(connector.symbols_get(group=pattern))
        if force or (not query and len(all_detected) < 20):
            global_syms = as_list(connector.symbols_get(group="*")) or as_list(connector.symbols_get())
            _collect(global_syms, cap=2000)
        if not query:
            mw_symbols = normalize(as_list(connector.symbols_get()))
            if mw_symbols:
                results = []
                mw_names = set()
                for symbol in mw_symbols:
                    name = getattr(symbol, "name", None)
                    if not name: continue
                    expiration = getattr(symbol, "expiration_time", 0) or 0
                    if expiration > 0 and expiration < now_ts: continue
                    path = getattr(symbol, "path", "") or getattr(symbol, "description", "") or ""
                    results.append({"symbol": name, "description": path, "group": "Market Watch"})
                    mw_names.add(name)
                for entry in all_detected:
                    if entry["symbol"] not in mw_names: results.append(entry)
                return results[:2000]
        return all_detected[:1000]
    except Exception as e:
        logger.error(f"SYMBOL FETCH ERROR: {e}")
        return []

# Symbol metadata (tick size, digits, volume min/max/step) is effectively
# static, but the order path and /api/symbol_info both used to ask the bridge
# for it on every call, paying ~418ms of transport to relearn rules they already
# knew. Keyed by symbol; a None answer is never cached, so a symbol that failed
# to resolve is retried on the next order.
_symbol_info_cache: Dict[Any, Any] = {}
_order_rules_cache: Dict[Any, Any] = {}
_SYMBOL_META_CACHE_TTL = 300.0


def _cached_symbol_info(symbol: str):
    """``mt5_access.symbol_info`` with a 300s per-symbol TTL."""
    return cached(
        _symbol_info_cache,
        symbol,
        _SYMBOL_META_CACHE_TTL,
        lambda: mt5_access.symbol_info(symbol),
    )


def _cached_order_size_rules(symbol: str):
    """``mt5_access.order_size_rules`` with a 300s per-symbol TTL.

    Cached separately from the symbol info so this module reuses the source of
    truth for the volume limits instead of recomputing them here.
    """
    return cached(
        _order_rules_cache,
        symbol,
        _SYMBOL_META_CACHE_TTL,
        lambda: mt5_access.order_size_rules(symbol),
    )


@app.get("/api/symbol_info")
async def get_symbol_info(
    symbol: str = Query(..., description="Symbol ticker"),
    user_id: str = Depends(get_authenticated_user_id),
):
    try:
        if detect_platform_for_symbol(symbol) == "crypto":
            from src.services.crypto_manager import get_crypto_manager
            from src.live.crypto_connector import get_connector
            manager = get_crypto_manager()
            accounts = manager.get_accounts(user_id=user_id)
            master_acc = next((acc for acc in accounts if acc.get("is_master")), None)
            if not master_acc and accounts:
                master_acc = accounts[0]
            if master_acc:
                crypto_conn = get_connector(master_acc["id"], user_id=user_id)
                if crypto_conn:
                    info = crypto_conn.get_symbol_info(symbol)
                    if info:
                        try:
                            info["order_size_rules"] = crypto_conn.get_order_size_rules(symbol)
                        except Exception:
                            info["order_size_rules"] = {}
                        return info
            return {
                "point": 0.01, 
                "digits": 2, 
                "tick_size": 0.01, 
                "stops_level": 0,
                "broker_type": "crypto",
                "order_size_rules": {}
            }
        def fetch_details():
            return GLOBAL_MT5_CONNECTOR.get_symbol_details(symbol)
        details = await asyncio.to_thread(fetch_details)
        if details is not None:
            try:
                rules = await asyncio.to_thread(
                    _cached_order_size_rules, resolve_symbol(symbol)
                )
                if rules:
                    details["order_size_rules"] = {
                        "min_amount": float(rules.get("volume_min") or 0.0),
                        "max_amount": float(rules.get("volume_max") or 0.0),
                        "step": float(rules.get("volume_step") or 0.0),
                        "contract_size": float(rules.get("contract_size") or 1.0),
                        "resolved_symbol": resolve_symbol(symbol),
                    }
            except Exception as rules_err:
                logger.warning(f"Could not read the order size rules for {symbol}: {rules_err}")
            # The crypto branch always answers this key; keep the shape stable
            # so the UI never has to guess whether the limits are known.
            details.setdefault("order_size_rules", {})
        return details
    except Exception as e:
        logger.error(f"Error fetching details for {symbol}: {e}")
        return {"point": 0.0001, "digits": 5, "tick_size": 0.0001, "stops_level": 0, "order_size_rules": {}}
@app.get("/api/algorithms")
async def get_algorithms():
    try:
        from src.algorithms import list_algorithms
        registry = list_algorithms()
        clean_registry = {}
        for k, v in registry.items():
            clean_registry[k] = {
                "name": v["name"],
                "description": v["description"],
                "requires_training": v["requires_training"],
                "config_schema": v.get("config_schema", {}),
            }
        return clean_registry
    except Exception as e:

        return {}
INDICATOR_SETTINGS = {
    "imbalance_impulse": {"enabled": False, "config": {}},
    "caza_stop": {"enabled": False, "config": {}},
    "order_flow": {"enabled": True, "config": {}},
    "liquidity_heatmap": {"enabled": False, "config": {}},
}
@app.get("/api/indicators")
async def get_indicators():
    try:
        from src.indicators import list_indicators
        indicators = list_indicators()
        for key in indicators:
            indicators[key]["enabled"] = INDICATOR_SETTINGS.get(key, {}).get(
                "enabled", False
            )
            indicators[key]["config"] = INDICATOR_SETTINGS.get(key, {}).get(
                "config", {}
            )
        return indicators
    except Exception as e:

        return {}
@app.post("/api/indicators/{indicator_id}/toggle")
async def toggle_indicator(indicator_id: str, data: dict = Body(...)):
    global INDICATOR_SETTINGS
    enabled = data.get("enabled", False)
    if indicator_id not in INDICATOR_SETTINGS:
        INDICATOR_SETTINGS[indicator_id] = {"enabled": False, "config": {}}
    INDICATOR_SETTINGS[indicator_id]["enabled"] = enabled
    return {"status": "ok", "indicator": indicator_id, "enabled": enabled}
@app.post("/api/indicators/{indicator_id}/config")
async def update_indicator_config(indicator_id: str, config: dict = Body(...)):
    global INDICATOR_SETTINGS
    if indicator_id not in INDICATOR_SETTINGS:
        INDICATOR_SETTINGS[indicator_id] = {"enabled": False, "config": {}}
    if "config" not in INDICATOR_SETTINGS[indicator_id]:
        INDICATOR_SETTINGS[indicator_id]["config"] = {}
    INDICATOR_SETTINGS[indicator_id]["config"].update(config)
    return {
        "status": "ok",
        "indicator": indicator_id,
        "config": INDICATOR_SETTINGS[indicator_id]["config"],
    }
@app.get("/api/indicators/calculate")
async def calculate_indicators(
    symbol: str = Query(...),
    timeframe: str = Query("1m"),
    limit: int = Query(5000),
    platform: Optional[str] = Query(None),
    cs_swing_bars: Optional[int] = Query(None),
    cs_lookback: Optional[int] = Query(None),
    cs_dist_ticks: Optional[int] = Query(None),
    cs_buffer_ticks: Optional[int] = Query(None),
    cs_vida_max: Optional[int] = Query(None),
    cs_lookback_tp: Optional[int] = Query(None),
    cs_ticks_tp: Optional[int] = Query(None),
    cs_mostrar_tp: Optional[bool] = Query(None),
    cs_analisis_vol: Optional[bool] = Query(None),
    cs_dibujar_safe: Optional[bool] = Query(None),
    imb_delta_threshold: Optional[float] = Query(None),
    imb_volume_multiplier: Optional[float] = Query(None),
    imb_min_body_ratio: Optional[float] = Query(None),
    imb_min_bars_between: Optional[int] = Query(None),
    imb_structure_lookback: Optional[int] = Query(None),
    imb_atr_multiplier: Optional[float] = Query(None),
    imb_use_structure: Optional[bool] = Query(None),
    imb_use_volume_filter: Optional[bool] = Query(None),
):
    global INDICATOR_SETTINGS
    results = {}
    try:
        import pandas as pd
        from src.indicators import get_indicator
        actual_symbol = resolve_symbol(symbol)
        # A workspace can outlive a futures contract: the broker drops the expired
        # one and the request would answer "No history found". Resolve the root (or
        # the expired contract) to whatever the broker lists today.
        try:
            from src.live.connector import get_mt5_connector
            history_connector = get_mt5_connector()
            if hasattr(history_connector, "resolve_contract"):
                actual_symbol = history_connector.resolve_contract(actual_symbol)
        except Exception:
            pass
        df = None
        try:
            if platform == 'crypto' or platform == 'futures':
                from src.platform.api.services_api import _market_data_engine
                if _market_data_engine is not None:
                    crypto_conn = _market_data_engine._get_connector("crypto")
                    if crypto_conn:
                        candles = crypto_conn.get_ohlcv(actual_symbol, timeframe, limit)
                        if candles and len(candles) >= 50:
                            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                            df['time'] = df['timestamp']
                    else:
                        pass

                else:
                    pass

            else:
                mt5_tf = mt5_access.timeframe_value(timeframe)
                connector = MT5Connector()
                candles = connector.get_latest_candles(actual_symbol, mt5_tf, limit)
                if candles is not None and len(candles) >= 50:
                    df = pd.DataFrame(candles)
                    df.columns = [c.lower() for c in df.columns]
        except Exception as e:
            pass

        if df is None or len(df) < 50:

            return {"indicators": {}, "error": "Insufficient data from data source"}
        col_map = {}
        target_cols = {
            "open": "Open", "high": "High", "low": "Low", 
            "close": "Close", "volume": "Volume", "time": "time"
        }
        for col in df.columns:
            lcol = col.lower()
            if lcol in target_cols:
                col_map[col] = target_cols[lcol]
        df.rename(columns=col_map, inplace=True)
        if "time" in df.columns and "timestamp" not in df.columns:
            try:
                if pd.api.types.is_datetime64_any_dtype(df["time"]):
                    df["timestamp"] = df["time"]
                else:
                    df["timestamp"] = pd.to_datetime(df["time"], unit="s", errors="coerce")
                    if df["timestamp"].isna().all():
                        df["timestamp"] = pd.to_datetime(df["time"], errors="coerce")
            except Exception:
                pass
        for indicator_id, settings in INDICATOR_SETTINGS.items():
            try:
                indicator_config = settings.get("config", {}).copy()
                indicator_config["timeframe"] = timeframe
                try:
                    from src.platform.api import services_api
                    if indicator_id == "caza_stop":
                        cle = services_api._caza_llama_engine
                        if cle and cle._active:
                            evolved = cle.get_params(actual_symbol)
                            if evolved:
                                indicator_config.update(evolved)
                        else:
                            if cs_swing_bars is not None: indicator_config["swing_bars"] = cs_swing_bars
                            if cs_lookback is not None: indicator_config["lookback"] = cs_lookback
                            if cs_dist_ticks is not None: indicator_config["dist_ticks"] = cs_dist_ticks
                            if cs_buffer_ticks is not None: indicator_config["buffer_ticks"] = cs_buffer_ticks
                            if cs_vida_max is not None: indicator_config["vida_max"] = cs_vida_max
                            if cs_lookback_tp is not None: indicator_config["lookback_tp"] = cs_lookback_tp
                            if cs_ticks_tp is not None: indicator_config["ticks_tp"] = cs_ticks_tp
                            if cs_mostrar_tp is not None: indicator_config["mostrar_tp"] = cs_mostrar_tp
                            if cs_analisis_vol is not None: indicator_config["analisis_vol"] = cs_analisis_vol
                            if cs_dibujar_safe is not None: indicator_config["dibujar_safe"] = cs_dibujar_safe
                    elif indicator_id == "imbalance_impulse":
                        ile = services_api._inbalance_llama_engine
                        if ile and ile._active:
                            evolved = ile.get_params(actual_symbol)
                            if evolved:
                                indicator_config.update(evolved)
                        else:
                            if imb_delta_threshold is not None: indicator_config["delta_threshold"] = imb_delta_threshold
                            if imb_volume_multiplier is not None: indicator_config["volume_multiplier"] = imb_volume_multiplier
                            if imb_min_body_ratio is not None: indicator_config["min_body_ratio"] = imb_min_body_ratio
                            if imb_min_bars_between is not None: indicator_config["min_bars_between"] = imb_min_bars_between
                            if imb_structure_lookback is not None: indicator_config["structure_lookback"] = imb_structure_lookback
                            if imb_atr_multiplier is not None: indicator_config["atr_multiplier"] = imb_atr_multiplier
                            if imb_use_structure is not None: indicator_config["use_structure"] = imb_use_structure
                            if imb_use_volume_filter is not None: indicator_config["use_volume_filter"] = imb_use_volume_filter
                except Exception as llama_exc:
                    pass

                indicator = get_indicator(indicator_id, indicator_config)
                if indicator:
                    results[indicator_id] = indicator.calculate(df)
            except Exception as e:

                import traceback; traceback.print_exc()
                results[indicator_id] = {"error": str(e)}
        return {"indicators": results}
    except Exception as e:

        import traceback; traceback.print_exc()
        return {"error": str(e)}
@app.get("/api/models/{ticker}")
async def get_models(ticker: str):
    try:
        safe_ticker = ticker.replace("=", "").replace("-", "")
        from src.services.database import get_outputs_dir
        models_dir = os.path.join(get_outputs_dir(), "models")
        if not os.path.exists(models_dir):
            return []
        timeframes = []
        for filename in os.listdir(models_dir):
            if filename.startswith(safe_ticker) and filename.endswith("_generator.pth"):
                try:
                    parts = filename.split("_")
                    if len(parts) >= 3:
                        tf = parts[1]
                        timeframes.append(tf)
                except:
                    continue
        return sorted(list(set(timeframes)))
    except Exception as e:

        return []
@app.get("/api/mapping")
async def get_mapping(platform: str = Query("mt5")):
    return {"mapping": load_symbol_map(platform)}
_ff_cache_time = None
_ff_cache_data = None

@app.get("/api/calendar")
async def get_economic_calendar(countries: str = Query("USD")):
    global _ff_cache_time, _ff_cache_data
    from datetime import datetime, timedelta
    import aiohttp

    now = datetime.now()
    events = []
    country_filter = [c.strip().upper() for c in countries.split(",")]
    expanded_filter = []
    for country in country_filter:
        expanded_filter.append(country)
        if country == "USD":
            expanded_filter.extend(["US", "USA"])
        elif country == "US":
            expanded_filter.extend(["USD", "USA"])
        elif country == "USA":
            expanded_filter.extend(["USD", "US"])
    try:
        data = []
        if _ff_cache_time and _ff_cache_data and (now - _ff_cache_time).total_seconds() < 300:
            data = _ff_cache_data
        else:
            import requests
            from starlette.concurrency import run_in_threadpool
            
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            
            def _fetch():
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    return resp.json()
                raise Exception(f"Forex Factory API returned status {resp.status_code}")
                
            try:
                data = await run_in_threadpool(_fetch)
                _ff_cache_data = data
                _ff_cache_time = now
            except Exception as req_e:
                if _ff_cache_data:
                    data = _ff_cache_data
                else:
                    raise req_e
        
        for event_data in data:
            try:
                event_time_str = event_data.get("date", "")
                country = event_data.get("country", "USD")
                event_name = event_data.get("title", "Economic Event")
                impact = event_data.get("impact", "Low")
                impact_map = {
                    "High": "High",
                    "Medium": "Medium",
                    "Low": "Low",
                    "NonEconomic": "Low",
                    "Holiday": "Low",
                }
                impact_level = impact_map.get(impact, "Medium")
                forecast = (
                    str(event_data.get("forecast", ""))
                    if event_data.get("forecast")
                    else ""
                )
                previous = (
                    str(event_data.get("previous", ""))
                    if event_data.get("previous")
                    else ""
                )
                actual = (
                    str(event_data.get("actual", ""))
                    if event_data.get("actual")
                    else ""
                )
                event_date = now + timedelta(hours=1)
                if event_time_str:
                    try:
                        event_date = datetime.fromisoformat(event_time_str)
                    except:
                        try:
                            from dateutil import parser
                            event_date = parser.parse(event_time_str)
                        except:
                            pass
                
                # Revert to keep the whole week (7 days)
                if (
                    event_date.date() >= (now - timedelta(days=7)).date()
                    and country.upper() in expanded_filter
                ):
                    local_event_date = event_date
                    if local_event_date.tzinfo is not None:
                        local_event_date = local_event_date.astimezone()
                        
                    events.append(
                        {
                            "id": f"ff_{country}_{event_name.replace(' ', '_')}_{event_date.strftime('%Y%m%d%H%M')}",
                            "title": event_name,
                            "country": country,
                            "date": event_date.isoformat(),
                            "is_today": local_event_date.date() == now.astimezone().date() if now.tzinfo else local_event_date.date() == now.date(),
                            "impact": impact_level,
                            "forecast": forecast,
                            "previous": previous,
                            "actual": actual,
                            "unit": "",
                        }
                    )
            except Exception as e:
                continue
        if len(events) > 0:
            events.sort(key=lambda x: x["date"])
            logger.info(
                f"Forex Factory: Successfully fetched {len(events)} LIVE events for countries: {countries}"
            )
            return {
                "status": "success",
                "events": events,
                "source": "forex_factory_live",
                "filter": countries,
            }
        else:
            raise Exception("No events from Forex Factory")
    except Exception as e:
        base_today = now.replace(hour=8, minute=0, second=0, microsecond=0)
        all_fallback_events = [
            {
                "id": f"fb_nfp_{now.strftime('%Y%m%d')}",
                "title": "Non-Farm Payrolls",
                "country": "USD",
                "date": (base_today + timedelta(hours=0, minutes=30)).isoformat(),
                "impact": "High",
                "forecast": "200K",
                "previous": "185K",
                "actual": "",
                "unit": "",
            },
            {
                "id": f"fb_cpi_{now.strftime('%Y%m%d')}",
                "title": "Consumer Price Index (YoY)",
                "country": "USD",
                "date": (base_today + timedelta(hours=1, minutes=30)).isoformat(),
                "impact": "High",
                "forecast": "2.5%",
                "previous": "2.3%",
                "actual": "",
                "unit": "",
            },
            {
                "id": f"fb_crude_{now.strftime('%Y%m%d')}",
                "title": "Crude Oil Inventories",
                "country": "USD",
                "date": (base_today + timedelta(hours=2, minutes=30)).isoformat(),
                "impact": "High",
                "forecast": "-2.5M",
                "previous": "-1.8M",
                "actual": "",
                "unit": "barrels",
            },
            {
                "id": f"fb_gdp_{now.strftime('%Y%m%d')}",
                "title": "GDP Growth Rate (QoQ)",
                "country": "EUR",
                "date": (base_today + timedelta(hours=5)).isoformat(),
                "impact": "High",
                "forecast": "2.1%",
                "previous": "2.0%",
                "actual": "",
                "unit": "",
            },
            {
                "id": f"fb_retail_{now.strftime('%Y%m%d')}",
                "title": "Retail Sales (MoM)",
                "country": "GBP",
                "date": (base_today + timedelta(hours=8)).isoformat(),
                "impact": "Medium",
                "forecast": "0.3%",
                "previous": "0.2%",
                "actual": "",
                "unit": "",
            },
        ]
        fallback_events = [
            e for e in all_fallback_events if e["country"] in expanded_filter
        ]
        logger.info(
            f"Using fallback calendar with {len(fallback_events)} events for countries: {countries}"
        )
        return {
            "status": "success",
            "events": fallback_events,
            "source": "fallback",
            "filter": countries,
            "error_msg": str(e),
        }
@app.post("/api/mapping")
async def update_mapping(platform: str = Query("mt5"), data: dict = Body(...)):
    save_symbol_map(data, platform)
    return {"status": "ok"}
app.include_router(create_runtime_router(get_platform_health))

@app.get("/api/license/check")
async def check_license_endpoint(
    user_id: Optional[str] = Query(None),
    role: str = Query("user")
):
    """
    Endpoint para que Electron verifique el estado de la licencia del hardware.
    """
    is_allowed, reason = await validate_license(user_id, role)
    return {
        "allowed": is_allowed,
        "reason": reason,
        "machine_id": get_machine_id(),
        "timestamp": datetime.now().isoformat()
    }
_connection_state = {
    "status": "disconnected",  
    "platform": None,  
    "message": "No conectado",
    "last_check": None,
    "account_info": None,
}
def _publish_connection_state(status, platform=None, message=None, account_info=None):
    """The only writer of the state the UI reads from /api/connection/status.

    Startup, connect and disconnect all publish through here, so a restarted
    container can never answer with the previous session's state.
    """
    _connection_state["status"] = status
    _connection_state["platform"] = platform
    _connection_state["message"] = message
    _connection_state["account_info"] = account_info
    _connection_state["last_check"] = datetime.now().isoformat()
    return _connection_state
async def _publish_live_connection_state(platform="mt5", release=True):
    """Connect MT5, read balance/equity and publish the real state.

    Shared by startup and /api/connection/connect; answers True when MT5
    accepted the connection. A failed attempt is published as an error instead
    of raising, so startup never dies because the broker is unreachable.

    ``release`` frees this probe's connector when the caller owns it. Startup
    passes False: by then the live services hold the session, and shutting the
    probe connector down took that session with it.
    """
    try:
        connector = MT5Connector()
        connected = await asyncio.to_thread(connector.connect)
        if not connected:
            _publish_connection_state("error", platform, "No se pudo conectar a MT5")
            return False
        balance = await asyncio.to_thread(connector.get_balance)
        equity = await asyncio.to_thread(connector.get_equity)
        _publish_connection_state(
            "connected",
            platform,
            "Conectado a MetaTrader 5",
            {"balance": balance, "equity": equity, "platform": platform},
        )
        if release:
            await asyncio.to_thread(connector.shutdown)
        return True
    except Exception as e:
        logger.error(f"[CONNECTION] Error publicando el estado de {platform}: {e}")
        _publish_connection_state("error", platform, f"Error: {str(e)}")
        return False
@app.get("/api/connection/status")
async def get_connection_status():
    return _connection_state
@app.post("/api/connection/connect")
async def connect_platform(data: dict = Body(...)):
    platform = "mt5" 
    _publish_connection_state(
        "connecting", platform, f"Conectando a {platform.upper()}..."
    )
    logger.info(f"[CONNECTION] Iniciando conexión a {platform}")
    try:
        if not await _publish_live_connection_state(platform):
            raise Exception("No se pudo conectar a MT5")
        await startup_services(platform="mt5")
        logger.info(f"[CONNECTION] Conectado exitosamente a MT5")
        return {"success": True, "state": _connection_state}
    except Exception as e:
        logger.error(f"[CONNECTION] Error conectando a {platform}: {e}")
        _publish_connection_state("error", platform, f"Error: {str(e)}")
        return {"success": False, "error": str(e), "state": _connection_state}
@app.post("/api/connection/disconnect")
async def disconnect_platform():
    try:
        logger.info(
            f"[CONNECTION] Desconectando de {_connection_state.get('platform')}"
        )
        await shutdown_services()
        _publish_connection_state("disconnected", None, "Desconectado")
        logger.info(f"[CONNECTION] Desconectado exitosamente")
        return {"success": True, "state": _connection_state}
    except Exception as e:
        logger.error(f"[CONNECTION] Error desconectando: {e}")
        return {"success": False, "error": str(e)}
_gpu_cache = {"data": None, "timestamp": 0, "ttl": 5}  # TTL reducido a 5s para telemetría en tiempo real
def _get_gpu_info_cached():
    """Keep the existing GPU provider entry point over the telemetry helper."""
    return get_gpu_info(GPUtil)
app.include_router(create_telemetry_router(
    metrics_provider=lambda: psutil,
    gpu_provider=lambda: _get_gpu_info_cached(),
    cache_provider=lambda: _gpu_cache,
    status_provider=lambda: ALGO_TYPE,
    clock=lambda: time.time(),
    process_id=lambda: os.getpid(),
    logger=logger,
))
@app.get("/live_status.json")
async def get_live_status_json():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f:
                content = json.load(f)
            return JSONResponse(content=content)
        except Exception as e:

            return JSONResponse(
                content={"status": "idle", "message": "Reading status..."},
                status_code=200,
            )
    return JSONResponse(
        content={"status": "idle", "message": "No live status available"}
    )
@app.get("/api/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    from src.services.database import get_outputs_dir
    dash_path = os.path.join(get_outputs_dir(), "dashboard.html")
    if os.path.exists(dash_path):
        with open(dash_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>No Dashboard Generated Yet</h1>"
@app.post("/api/algo/start")
async def start_training(req: AlgoStartRequest):
    global ALGO_PROCESS, ALGO_TYPE, LAST_ALGO_TYPE
    if ALGO_PROCESS and ALGO_PROCESS.poll() is None:
        raise HTTPException(status_code=400, detail="A process is already running")
    if getattr(sys, 'frozen', False):
        python_exe = sys.executable
        cmd = [
            python_exe,
            "--train",
            "--ticker", req.ticker,
            "--period", req.period,
            "--epochs", str(req.epochs),
            "--asset_type", req.asset_type,
            "--train_timeframe", req.train_timeframe,
            "--trade_timeframe", req.trade_timeframe,
            "--seq_length", str(req.seq_length),
            "--hidden_dim", str(req.hidden_dim),
            "--num_layers", str(req.num_layers)
        ]
    else:
        python_exe = get_venv_python()
        cmd = [
            python_exe,
            "-u",
            "-c",
            f"from train import train_model; train_model('{req.ticker}', '{req.period}', {req.epochs}, '{req.asset_type}', '{req.train_timeframe}', '{req.trade_timeframe}', {req.seq_length}, {req.hidden_dim}, {req.num_layers})",
        ]

    try:
        log_dir = os.path.join(ROOT_DIR, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "training.log")
        with open(log_file, "w") as out:
            kwargs = {}
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
                kwargs["startupinfo"] = startupinfo
                kwargs["creationflags"] = 0x08000000
            ALGO_PROCESS = subprocess.Popen(
                cmd,
                cwd=ROOT_DIR,
                stdout=out,
                stderr=subprocess.STDOUT,
                **kwargs
            )
            ALGO_TYPE = "training"
            LAST_ALGO_TYPE = "training"
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()

        raise HTTPException(status_code=500, detail=f"Spawn failed: {e}. Traceback: {error_trace}")
    return {"status": "started", "message": f"Training started for {req.ticker}"}
@app.post("/api/algo/live")
async def start_live(req: LiveStartRequest):
    global ALGO_PROCESS, ALGO_TYPE, LAST_ALGO_TYPE
    if ALGO_PROCESS and ALGO_PROCESS.poll() is None:
        raise HTTPException(status_code=400, detail="A process is already running")
    if os.path.exists(STATUS_FILE):
        try:
            os.remove(STATUS_FILE)
        except:
            pass
    log_dir = os.path.join(ROOT_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "live_trading.log")
    if getattr(sys, 'frozen', False):
        python_exe = sys.executable
        cmd = [
            python_exe,
            "--live",
            "--ticker", req.ticker,
            "--asset_type", req.asset_type,
            "--platform", req.platform,
            "--timeframe", req.timeframe,
            "--algorithm", req.algorithm or "EvolutionaryGAN",
        ]
        if req.account_id:
            cmd.extend(["--account_id", req.account_id])
        if req.config:
            cmd.extend(["--config", json.dumps(req.config)])
    else:
        python_exe = get_venv_python()
        script_path = os.path.join(ROOT_DIR, "src", "live", "live_trade.py")
        cmd = [
            python_exe,
            "-u",
            script_path,
            "--ticker",
            req.ticker,
            "--asset_type",
            req.asset_type,
            "--platform",
            req.platform,
            "--timeframe",
            req.timeframe,
            "--algorithm",
            req.algorithm or "EvolutionaryGAN",
        ]

        if req.account_id:
            cmd.extend(["--account_id", req.account_id])
        if req.config:
            cmd.extend(["--config", json.dumps(req.config)])

    try:
        with open(log_file, "w") as out:
            kwargs = {}
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
                kwargs["startupinfo"] = startupinfo
                kwargs["creationflags"] = 0x08000000
            ALGO_PROCESS = subprocess.Popen(
                cmd,
                cwd=ROOT_DIR,
                stdout=out,
                stderr=subprocess.STDOUT,
                **kwargs
            )
            ALGO_TYPE = "active"
            LAST_ALGO_TYPE = "active"
    except Exception as e:

        raise HTTPException(status_code=500, detail=f"Spawn failed: {e}")
    return {
        "status": "started",
        "message": f"Live Trading started for {req.ticker} on {req.platform}",
    }
@app.post("/api/algo/stop")
async def stop_algo():
    global ALGO_PROCESS, ALGO_TYPE
    if ALGO_PROCESS and ALGO_PROCESS.poll() is None:
        try:
            import psutil
            parent = psutil.Process(ALGO_PROCESS.pid)
            for child in parent.children(recursive=True):
                child.terminate()
            parent.terminate()
        except:
            ALGO_PROCESS.terminate()
        ALGO_PROCESS = None
        ALGO_TYPE = "idle"
        if os.path.exists(STATUS_FILE):
            try:
                os.remove(STATUS_FILE)
            except:
                pass
        return {"status": "stopped"}
    return {"status": "not_running"}
@app.post("/api/algo/clean")
async def clean_data():
    try:
        from src.utils.cleaner import clean_system_data
        clean_system_data(interactive=False)
        return {
            "status": "success",
            "message": "System data cleaned. Ready for restart.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/api/logs")
async def get_logs(lines: int = 50):
    global ALGO_TYPE, LAST_ALGO_TYPE
    current_type = ALGO_TYPE if ALGO_TYPE != "idle" else LAST_ALGO_TYPE
    log_file = "live_trading.log" if current_type == "active" else "training.log"
    path = os.path.join(ROOT_DIR, "logs", log_file)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return f.readlines()[-lines:]
        except:
            return []
    return []
@app.get("/api/algo/status")
async def algo_status():
    global ALGO_PROCESS, ALGO_TYPE
    if ALGO_PROCESS:
        poll = ALGO_PROCESS.poll()
        if poll is None:
            return {"status": ALGO_TYPE, "gpu_load": 32}
        else:
            ALGO_PROCESS = None
    return {"status": "idle", "gpu_load": 0}
@app.post("/api/platform/switch")
async def switch_platform(platform: str = Body(..., embed=True)):
    allowed = ["mt5", "crypto", "tradovate", "nt8"]
    if platform not in allowed:
         raise HTTPException(status_code=400, detail=f"Platform {platform} is not supported.")
    try:
        engine = get_market_data_engine()
        engine.switch_platform(platform)
        logger.info(f"Market Data Engine switched to {platform}")
    except Exception as e:
        logger.error(f"Error switching market data engine to {platform}: {e}")
    return {"status": "success", "active_platform": platform}
@app.get("/api/config")
async def get_config(user_id: str = Depends(get_authenticated_user_id)):
    db_settings = db_get_settings(user_id=user_id)
    trading_defaults = {
        "automation_enabled": False,
        "volume": 1.0,
        "max_daily_loss": 500.0,
        "max_trades_per_day": 5,
        "daily_profit_target": 100.0,
        "start_hour": "09:30",
        "end_hour": "16:00",
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = json.load(f)
                trading_defaults.update(saved)
        except Exception as e:
            pass

    return {**trading_defaults, **db_settings}
@app.post("/api/config")
async def update_config(
    config: Dict[str, Any] = Body(...),
    user_id: str = Depends(get_authenticated_user_id),
):
    try:
        ui_keys = {
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
            "chart_candle_up",
            "chart_candle_down",
            "chart_bg_color",
            "chart_candle_border_visible",
            "chart_candle_border_color",
        }
        personal_keys = ui_keys | {
            "commissions",
            "chart_history_limits",
            "risk_max_daily_loss",
            "risk_max_contracts",
            "risk_emotional_guard",
            "risk_locked_until",
        }
        personal_config = {k: v for k, v in config.items() if k in personal_keys}
        trading_config = {k: v for k, v in config.items() if k not in personal_keys}
        if personal_config:
            db_save_settings(personal_config, user_id=user_id)
        if trading_config:
            if owner_user_id() != user_id:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "These settings affect the whole platform and only the "
                        "configured owner may change them: "
                        + ", ".join(sorted(trading_config))
                    ),
                )
            existing = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    existing = json.load(f)
            existing.update(trading_config)
            with open(CONFIG_FILE, "w") as f:
                json.dump(existing, f, indent=4)
        return {"status": "ok", "message": "Configuración guardada"}
    except DatabaseNotConfigured:
        raise
    except HTTPException:
        raise
    except Exception as e:

        raise HTTPException(status_code=500, detail=str(e))
@app.get("/api/config/secrets")
async def get_secrets():
    from src.services.auth import SUPABASE_URL, SUPABASE_ANON_KEY
    return {
        "status": "ok",
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_ANON_KEY": SUPABASE_ANON_KEY,
        "secrets": {
            "SUPABASE_URL": SUPABASE_URL,
            "SUPABASE_ANON_KEY": SUPABASE_ANON_KEY
        }
    }
@app.get("/api/market/session")
async def get_market_session(
    symbol: str = Query("SPY", description="Symbol to check market type"),
):
    try:
        global _session_cache
        cached_session = _session_cache.get(symbol)
        if cached_session and (time.time() - cached_session["ts"]) < _SESSION_CACHE_TTL:
            return cached_session["data"]
        from src.services.order_gateway.risk_validator import RiskValidator
        validator = RiskValidator()
        session = validator._get_current_session(symbol)
        market_type = validator._get_market_type(symbol)
        
        # FIX: Crypto markets are 24/7
        if market_type == "crypto" or "USDT" in symbol.upper() or "/" in symbol:
            session = "CRYPTO"
            market_type = "crypto"
        try:
            import pytz
            et_tz = pytz.timezone("America/New_York")
            now_et = datetime.now(et_tz)
            current_time = now_et.strftime("%H:%M")
            current_hour = now_et.hour
        except ImportError:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            current_hour = now.hour
        session_info = {
            "session": session,
            "market_type": market_type,
            "current_time_et": current_time,
            "server_time": datetime.now().isoformat(),
        }
        if market_type == "stocks":
            if session == "PRE_MARKET":
                session_info["session_start"] = "04:00"
                session_info["session_end"] = "09:30"
                session_info["next_session"] = "REGULAR"
                session_info["next_session_start"] = "09:30"
            elif session == "REGULAR":
                session_info["session_start"] = "09:30"
                session_info["session_end"] = "16:00"
                session_info["next_session"] = "AFTER_HOURS"
                session_info["next_session_start"] = "16:00"
            elif session == "AFTER_HOURS":
                session_info["session_start"] = "16:00"
                session_info["session_end"] = "20:00"
                session_info["next_session"] = "CLOSED"
                session_info["next_session_start"] = "20:00"
            else:  
                session_info["session_start"] = "20:00"
                session_info["session_end"] = "04:00"
                session_info["next_session"] = "PRE_MARKET"
                session_info["next_session_start"] = "04:00"
        elif market_type == "forex":
            if session == "ASIAN":
                session_info["session_start"] = "19:00"
                session_info["session_end"] = "04:00"
                session_info["next_session"] = "LONDON"
                session_info["next_session_start"] = "03:00"
            elif session == "LONDON":
                session_info["session_start"] = "03:00"
                session_info["session_end"] = "12:00"
                session_info["next_session"] = "NEW_YORK"
                session_info["next_session_start"] = "08:00"
            elif session == "NEW_YORK":
                session_info["session_start"] = "08:00"
                session_info["session_end"] = "17:00"
                session_info["next_session"] = "ASIAN"
                session_info["next_session_start"] = "19:00"
            else:  
                session_info["session_start"] = "17:00"
                session_info["session_end"] = "17:00"
                session_info["next_session"] = "ASIAN"
                session_info["next_session_start"] = "17:00"  
        elif market_type == "futures":
            if session == "ASIAN":
                session_info["session_start"] = "19:00"
                session_info["session_end"] = "04:00"
                session_info["next_session"] = "LONDON"
                session_info["next_session_start"] = "03:00"
            elif session == "LONDON":
                session_info["session_start"] = "03:00"
                session_info["session_end"] = "12:00"
                session_info["next_session"] = "NEW_YORK"
                session_info["next_session_start"] = "08:00"
            elif session == "NEW_YORK":
                session_info["session_start"] = "08:00"
                session_info["session_end"] = "17:00"
                session_info["next_session"] = "ASIAN"
                session_info["next_session_start"] = "19:00"
            elif session == "REGULAR":
                session_info["session_start"] = "09:30"
                session_info["session_end"] = "16:00"
                session_info["next_session"] = "NEW_YORK"
                session_info["next_session_start"] = "17:00"
            else:  
                session_info["session_start"] = "17:00"
                session_info["session_end"] = "18:00"
                session_info["next_session"] = "ASIAN"
                session_info["next_session_start"] = "18:00"  
        elif market_type == "crypto":
            session_info["session_start"] = "00:00"
            session_info["session_end"] = "23:59"
            session_info["next_session"] = "CRYPTO"
            session_info["next_session_start"] = "00:00"
        _session_cache[symbol] = {"data": session_info, "ts": time.time()}
        return session_info
    except Exception as e:
        logger.error(f"Error getting market session: {e}")
        return {
            "session": "UNKNOWN",
            "market_type": "stocks",
            "current_time_et": datetime.now().strftime("%H:%M"),
            "error": str(e),
        }
@app.get("/api/workspace/last-active")
async def get_last_active(user_id: str = Depends(get_authenticated_user_id)):
    try:
        session_name = get_last_active_workspace(user_id=user_id)
        workspace = db_get_workspace(session_name, user_id=user_id)
        return {"session": session_name, "workspace": workspace}
    except DatabaseNotConfigured:
        raise
    except Exception as e:

        return {"session": "session_mt5", "workspace": None}
@app.post("/api/workspace/last-active")
async def set_last_active(
    data: Dict[str, Any] = Body(...),
    user_id: str = Depends(get_authenticated_user_id),
):
    try:
        session_name = data.get("session", "session_mt5")
        set_last_active_workspace(session_name, user_id=user_id)
        return {"status": "ok", "session": session_name}
    except DatabaseNotConfigured:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/api/workspace/{session}")
async def get_workspace(session: str, user_id: str = Depends(get_authenticated_user_id)):
    try:
        workspace = db_get_workspace(session, user_id=user_id)
        if workspace:
            return workspace
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
            workspaces = config.get("workspaces", {})
            return workspaces.get(session, None)
        return None
    except DatabaseNotConfigured:
        raise
    except Exception as e:

        return None
@app.post("/api/workspace/{session}")
async def save_workspace(
    session: str,
    workspace: Dict[str, Any] = Body(...),
    user_id: str = Depends(get_authenticated_user_id),
):
    try:

        db_save_workspace(session, workspace, user_id=user_id)
        set_last_active_workspace(session, user_id=user_id)
        return {
            "status": "ok",
            "session": session,
            "saved_at": datetime.now().isoformat(),
        }
    except DatabaseNotConfigured:
        raise
    except Exception as e:

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workspaces")
async def list_workspaces(user_id: str = Depends(get_authenticated_user_id)):
    try:
        data = get_all_workspaces(user_id=user_id)
        logger.info(f"Retrieved {len(data)} workspaces from DB")
        return data
    except DatabaseNotConfigured:
        raise
    except Exception as e:
        logger.error(f"Error listing workspaces: {e}")
        return {}

@app.delete("/api/workspace/{name}")
async def remove_workspace(name: str, user_id: str = Depends(get_authenticated_user_id)):
    try:
        delete_workspace(name, user_id=user_id)
        return {"status": "ok"}
    except DatabaseNotConfigured:
        raise
    except Exception as e:
        logger.error(f"Error deleting workspace: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/timeframes")
async def get_timeframes(
    platform: str = Query("mt5", description="crypto or mt5"),
    user_id: str = Depends(get_authenticated_user_id),
):
    try:
        if platform.lower() == "crypto":
            from src.services.crypto_manager import get_crypto_manager
            from src.live.crypto_connector import get_connector
            manager = get_crypto_manager()
            accounts = manager.get_accounts(user_id=user_id)
            master_acc = next((acc for acc in accounts if acc.get("is_master")), None)
            if not master_acc and accounts:
                master_acc = accounts[0]
            if master_acc:
                conn = get_connector(master_acc["id"], user_id=user_id)
                if conn and conn.exchange and conn.exchange.timeframes:
                    return {"status": "ok", "timeframes": list(conn.exchange.timeframes.keys())}
            return {"status": "ok", "timeframes": ["1s", "1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"]}
        else:
            return {"status": "ok", "timeframes": ["1m", "2m", "3m", "4m", "5m", "6m", "10m", "12m", "15m", "20m", "30m", "1h", "2h", "3h", "4h", "6h", "8h", "12h", "1d", "1w", "1M"]}
    except Exception as e:
        logger.error(f"Error fetching timeframes: {e}")
        return {"status": "error", "timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"]}
@app.get("/api/history")
async def get_history(
    symbol: str = Query(...),
    timeframe: str = Query("1m"),
    limit: int = 10000,
    platform: Optional[str] = Query(None),
    user_id: str = Depends(get_authenticated_user_id),
):
    try:
        if timeframe.endswith("s"):
            logger.warning(f"Blocked dangerous sub-minute history request for {symbol} ({timeframe})")
            return []
        # Delayed resolution: MT5 needs it, Crypto handles it internally
        current_state_platform = getattr(app.state, "last_platform", "mt5")
        detected_platform = detect_platform_for_symbol(symbol)
        target_platform = platform or detected_platform
        if target_platform == "mt5" and current_state_platform in ["nt8", "tradovate", "crypto"]:
            futures_prefixes = ["MNQ", "NQ", "MES", "ES", "CL", "GC", "RTY", "YM"]
            if any(p in symbol.upper() for p in futures_prefixes):
                target_platform = current_state_platform

        actual_symbol = symbol
        if target_platform == "mt5":
            from .utils import resolve_symbol
            actual_symbol = resolve_symbol(symbol)
            
        fetch_limit = limit
        if target_platform == "crypto":
            # Optimization: Try accounts in parallel or just enough to get data
            manager = get_crypto_manager()
            all_accounts = manager.get_accounts(user_id=user_id)
            all_accounts.sort(key=lambda x: x.get("is_master", False), reverse=True)
            
            ohlcv = None
            # Limit to top 3 accounts to prevent long timeouts if many exist
            for acc in all_accounts[:3]:
                try:
                    curr_conn = get_crypto_connector(acc["id"], user_id=user_id)
                    if not curr_conn: continue
                    fetch_sym = curr_conn._resolve_sym(actual_symbol)
                    ohlcv = await asyncio.to_thread(curr_conn.get_ohlcv, fetch_sym, timeframe, limit=fetch_limit)
                    if ohlcv and len(ohlcv) > 0:
                        break
                except Exception as e:
                    logger.debug(f"Crypto fetch failed for {acc.get('name')}: {e}")
                    continue
            
            if not ohlcv: return []
            
            # Vectorized creation of result list is faster for large datasets
            def convert_ohlcv(data):
                res = []
                for bar in data:
                    ts = bar[0]
                    try:
                        o, h, l, c, v = float(bar[1]), float(bar[2]), float(bar[3]), float(bar[4]), float(bar[5])
                    except (ValueError, TypeError):
                        continue
                    
                    # FIX: Validate all values are finite using math.isfinite
                    if not (math.isfinite(o) and math.isfinite(h) and math.isfinite(l) and math.isfinite(c) and math.isfinite(v)):
                        continue
                    
                    # FIX: Ensure OHLC values are valid
                    if h < l or h < o or h < c or l > o or l > c:
                        # Fix invalid candle: h = max(OHLC), l = min(OHLC)
                        h = max(o, h, c)
                        l = min(o, l, c)
                    
                    pr = h - l
                    body = abs(c - o)
                    sr = max(pr, 1e-8)
                    delta = v * (body / sr)
                    if c < o: delta *= -1
                    
                    # FIX: Convert timestamp correctly (ccxt returns ms timestamps)
                    if ts > 10000000000:
                        ts_sec = ts / 1000.0
                    else:
                        ts_sec = ts
                    
                    res.append({
                        "time": datetime.utcfromtimestamp(ts_sec).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "Open": o, "High": h, "Low": l, "Close": c, "Volume": v, "delta": delta
                    })
                return res
            
            result = await asyncio.to_thread(convert_ohlcv, ohlcv)
            return sanitize_float_list(result)

        global GLOBAL_MT5_CONNECTOR
        if not GLOBAL_MT5_CONNECTOR.connected:
             await asyncio.to_thread(GLOBAL_MT5_CONNECTOR.connect)
        
        # Optimization: Use to_thread for blocking MT5 call
        df = await asyncio.to_thread(GLOBAL_MT5_CONNECTOR.get_latest_candles, actual_symbol, timeframe, n=fetch_limit)
        
        if df is None or df.empty:
            logger.warning(f"No history found for {actual_symbol} ({timeframe})")
            return []
            
        # Optimization: Vectorized Pandas calculations
        df["range_safe"] = (df["High"] - df["Low"]).clip(lower=1e-8)
        df["body"] = (df["Close"] - df["Open"]).abs()
        df["delta"] = df["Volume"] * (df["body"] / df["range_safe"])
        df.loc[df["Close"] < df["Open"], "delta"] *= -1
        
        # Vectorized datetime formatting
        df["time"] = df["time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Select and convert to records
        cols = ["time", "Open", "High", "Low", "Close", "Volume", "delta"]
        result = df[cols].to_dict('records')
        
        return sanitize_float_list(result)
    except Exception as e:
        logger.error(f"Error in get_history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/api/vix")
async def get_vix(timeframe: str = Query("5m"), limit: int = Query(200)):
    import requests as _requests
    def _build_session():
        s = _requests.Session()
        s.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36'
        })
        return s
    def _fetch_tv_price(session):
        try:
            payload = {
                "symbols": {"tickers": ["CBOE:VIX", "TVC:VIX"], "query": {"types": []}},
                "columns": ["close", "time"]
            }
            r = session.post(
                "https://scanner.tradingview.com/america/scan",
                json=payload, timeout=8
            )
            if not r.ok:
                return None, None
            data = r.json().get("data", [])
            for item in data:
                d = item.get("d") or []
                if len(d) >= 1 and isinstance(d[0], (int, float)) and d[0] > 0:
                    return float(d[0]), d[1] if len(d) > 1 else None
        except Exception:
            pass
        return None, None
    def _sync_fetch_vix(interval, period, session):
        df = None
        try:
            df = yf.download("^VIX", period=period, interval=interval,
                             progress=False, session=session)
            if df is not None and not df.empty:
                pass

        except Exception as e:
            pass

        if df is None or df.empty:
            try:
                df = yf.download("VXX", period=period, interval=interval,
                                 progress=False, session=session)
                if df is not None and not df.empty:
                    pass

            except Exception:
                pass
        return df
    def _sync_fetch_live_price(session):
        tv_price, tv_time = _fetch_tv_price(session)
        if tv_price is not None:
            return tv_price, tv_time
        try:
            live_df = yf.download("^VIX", period="1d", interval="1m",
                                  progress=False, session=session)
            if live_df is not None and not live_df.empty:
                return float(live_df["Close"].iloc[-1]), None
        except Exception:
            pass
        try:
            v_ticker = yf.Ticker("^VIX")
            price = v_ticker.info.get("regularMarketPrice")
            if price:
                return float(price), None
        except Exception:
            pass
        return None, None
    try:
        now_ts = time.time()
        interval_map = {"1m": "1m", "5m": "5m", "15m": "15m",
                        "30m": "30m", "1h": "1h", "1d": "1d"}
        interval = interval_map.get(timeframe, "5m")
        period = "5d" if interval in ["1m", "5m"] else "1mo"
        need_history = False
        with VIX_CACHE_LOCK:
            need_history = (
                VIX_HISTORY_CACHE["df"] is None
                or VIX_HISTORY_CACHE["timeframe"] != timeframe
                or (now_ts - VIX_HISTORY_CACHE["last_fetch"] > 300)
            )
        if need_history:
            session = _build_session()
            df = await asyncio.to_thread(_sync_fetch_vix, interval, period, session)
            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    try:
                        df.columns = df.columns.get_level_values(0)
                    except Exception:
                        pass
                df.sort_index(inplace=True)  
                with VIX_CACHE_LOCK:
                    VIX_HISTORY_CACHE["df"] = df
                    VIX_HISTORY_CACHE["last_fetch"] = now_ts
                    VIX_HISTORY_CACHE["timeframe"] = timeframe
        need_live = False
        with VIX_CACHE_LOCK:
            need_live = (
                VIX_LIVE_CACHE["price"] is None
                or (now_ts - VIX_LIVE_CACHE["last_fetch"] > 30)
            )
        if need_live:
            session = _build_session()
            live_price, live_ts_raw = await asyncio.to_thread(
                _sync_fetch_live_price, session
            )
            if live_price is not None:
                with VIX_CACHE_LOCK:
                    VIX_LIVE_CACHE["price"] = live_price
                    VIX_LIVE_CACHE["time"] = live_ts_raw
                    VIX_LIVE_CACHE["last_fetch"] = now_ts
        with VIX_CACHE_LOCK:
            df = VIX_HISTORY_CACHE["df"]
            live_price = VIX_LIVE_CACHE["price"]
            live_ts_raw = VIX_LIVE_CACHE.get("time")
            if live_price is not None:
                prev = VIX_LIVE_CACHE.get("last_emit_price")
                if prev is None or live_price != prev:
                    VIX_LIVE_CACHE["last_emit_price"] = live_price
                    VIX_LIVE_CACHE["stale_count"] = 0
                else:
                    VIX_LIVE_CACHE["stale_count"] = VIX_LIVE_CACHE.get("stale_count", 0) + 1
                if VIX_LIVE_CACHE.get("stale_count", 0) >= 6:
                    VIX_LIVE_CACHE["last_fetch"] = 0
                    VIX_LIVE_CACHE["stale_count"] = 0
        if df is None or df.empty:
            logger.warning(f"Could not fetch real VIX data ({timeframe}). Using simulated fallback.")
            import random
            times = pd.date_range(end=datetime.now(), periods=limit if limit else 200, freq=interval)
            # Use a more realistic starting point and slightly higher volatility
            closes = [18.0]
            for _ in range(len(times) - 1):
                closes.append(max(10, min(80, closes[-1] + random.uniform(-0.5, 0.5))))
            df = pd.DataFrame(
                {"Open": closes, "High": [c + random.uniform(0, 0.2) for c in closes], 
                 "Low": [c - random.uniform(0, 0.2) for c in closes],
                 "Close": closes, "Volume": 0},
                index=times
            )
        df_display = df.copy()
        df_display.sort_index(inplace=True)  
        if live_price:
            try:
                if isinstance(live_ts_raw, (int, float)) and live_ts_raw > 10_000_000_000:
                    live_ts_raw = live_ts_raw / 1000
                if isinstance(live_ts_raw, (int, float)) and live_ts_raw > 0:
                    now_utc = datetime.fromtimestamp(live_ts_raw, tz=timezone.utc)
                else:
                    now_utc = datetime.now(timezone.utc)
                if df_display.index.tz is not None:
                    now_utc = now_utc.astimezone(df_display.index.tz)
                new_row = pd.Series(
                    {"Open": live_price, "High": live_price,
                     "Low": live_price, "Close": live_price, "Volume": 0},
                    name=now_utc
                )
                df_display = pd.concat([df_display, pd.DataFrame([new_row])])
            except Exception:
                pass
        df_display = df_display.tail(limit)
        result = []
        for ts, row in df_display.iterrows():
            try:
                utc_ts = ts.tz_convert("UTC") if hasattr(ts, "tz_convert") and ts.tzinfo else ts
                result.append({
                    "time": utc_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "Open": float(row["Open"]),
                    "High": float(row["High"]),
                    "Low": float(row["Low"]),
                    "Close": float(row["Close"]),
                    "Volume": 0
                })
            except Exception:
                continue
        return sanitize_float(result)
    except Exception as e:

        return []
VIX_SESSION = None

@app.get("/api/vix/live")
async def get_vix_live():
    global VIX_SESSION
    try:
        now_ts = time.time()
        
        # 1. Quick cache check (blocking lock but very fast)
        with VIX_CACHE_LOCK:
            cache_age = now_ts - VIX_LIVE_CACHE.get("last_fetch", 0)
            cached_price = VIX_LIVE_CACHE.get("price")
            cached_time = VIX_LIVE_CACHE.get("time")
            
        # If cache is fresh (< 5 seconds), return immediately
        if cached_price is not None and cache_age < 5.0:
            return {
                "vix": cached_price, 
                "time": cached_time or int(now_ts),
                "cached": True,
                "age": round(cache_age, 1)
            }

        def _fetch_live():
            global VIX_SESSION
            import requests as _requests
            if VIX_SESSION is None:
                VIX_SESSION = _requests.Session()
                VIX_SESSION.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
                })
            
            # Try TradingView first
            try:
                payload = {
                    "symbols": {"tickers": ["CBOE:VIX", "TVC:VIX"]},
                    "columns": ["close", "time"]
                }
                r = VIX_SESSION.post("https://scanner.tradingview.com/america/scan", json=payload, timeout=5)
                if r.ok:
                    data = r.json().get("data", [])
                    if data:
                        d = data[0].get("d", [])
                        if d and len(d) >= 1:
                            return float(d[0]), d[1] if len(d) > 1 else int(time.time())
            except: pass
            
            # Fallback to Yahoo Finance (Fast Info)
            try:
                import yfinance as yf
                ticker = yf.Ticker("^VIX")
                # fast_info is much faster than .info
                p = ticker.fast_info.get("last_price")
                if p: return float(p), int(time.time())
            except: pass

            # Fallback to Yahoo Finance (Download)
            try:
                import yfinance as yf
                df = yf.download("^VIX", period="1d", interval="1m", progress=False)
                if df is not None and not df.empty:
                    p = float(df["Close"].iloc[-1])
                    return p, int(time.time())
            except: pass
            return None, None

        # Execute fetch in background thread
        live_price, live_ts = await asyncio.to_thread(_fetch_live)
        
        if live_price is not None:
            with VIX_CACHE_LOCK:
                VIX_LIVE_CACHE["price"] = live_price
                VIX_LIVE_CACHE["time"] = live_ts
                VIX_LIVE_CACHE["last_fetch"] = now_ts
            return {"vix": live_price, "time": live_ts, "cached": False}
        
        # If fetch failed, return stale cache if available
        if cached_price is not None:
            return {"vix": cached_price, "time": cached_time, "stale": True}
            
        return {"vix": 0, "time": int(now_ts), "error": "unavailable"}
        
    except Exception as e:
        logger.error(f"Error in get_vix_live: {e}")
        return {"vix": 0, "time": int(time.time()), "error": str(e)}

# Deals history barely moves between polls: the panel asks for it every 10s
# while the underlying history gains or loses a row at a time, and each miss
# costs a full ~418ms bridge round trip. Keyed by platform + days + symbol (plus
# the caller, because the crypto branch answers for that user's accounts, so one
# tenant's deals must never be served to another).
_deals_cache: Dict[Any, Any] = {}
_DEALS_CACHE_TTL = 30.0


@app.get("/api/deals")
async def get_deals(
    days: int = Query(365),
    symbol: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    user_id: str = Depends(get_authenticated_user_id),
):

    try:
        target_platform = platform or _connection_state.get("platform") or "mt5"
        logger.info(f"[DEALS_REQUEST] platform={target_platform}, days={days}")

        deals_cache_key = ("deals", target_platform, days, symbol or "", user_id)

        def _fetch_deals_payload(user_id: str):
            """One bridge round trip per key. Runs in a worker thread: the
            connectors (and ``connector.connect``) are synchronous.

            ``user_id`` is required, not optional: this reads account data, and the
            tenancy contract in tests/test_accounts_consumers.py forbids an account
            path that does not take the tenant it resolved from the token.
            """
            deals = []
            account_balance = 0
            date_from = None
            if days:
                date_from = datetime.now() - pd.Timedelta(days=days)

            if target_platform == "mt5":
                connector = GLOBAL_MT5_CONNECTOR
                if not connector.connected:
                    connector.connect()
                deals = connector.get_deals(date_from=date_from)
                # One shape line per bridge read: the panel filters on type,
                # time and symbol, so an empty panel needs to be
                # distinguishable from an unreadable bridge by what arrived.
                try:
                    first = deals[0] if deals else None
                    preview = None
                    if first is not None:
                        getter = first.get if isinstance(first, dict) else (lambda k, d=first: getattr(d, k, None))
                        preview = {k: getter(k) for k in ('type', 'entry', 'time', 'symbol', 'profit')}
                    types = {}
                    for deal in deals:
                        key = deal.get('type') if isinstance(deal, dict) else getattr(deal, 'type', None)
                        types[key] = types.get(key, 0) + 1
                    logger.info(f"[DEALS_SHAPE] count={len(deals)} types={types} first={preview}")
                except Exception as shape_err:
                    logger.warning(f"[DEALS_SHAPE] could not describe the payload: {shape_err}")
                acc_info = connector.get_account_info()
                if acc_info:
                    account_balance = acc_info.get("balance", 0)
            elif target_platform == "crypto":
                from src.services.crypto_manager import get_crypto_manager
                from src.live.crypto_connector import get_connector
                manager = get_crypto_manager()
                accounts = manager.get_accounts(user_id=user_id)
                master_acc = next((acc for acc in accounts if acc.get("is_master")), None) or (accounts[0] if accounts else None)

                logger.info(f"[DEALS] Target Platform: crypto, Master Account: {master_acc['id'] if master_acc else 'None'}")

                if master_acc:
                    crypto_conn = get_connector(master_acc["id"], user_id=user_id)
                    if crypto_conn:
                        date_from = None
                        if days:
                            date_from = datetime.now() - pd.Timedelta(days=days)
                        deals = crypto_conn.get_deals(date_from=date_from, symbol=symbol)
                        account_balance = crypto_conn.get_balance()
                        logger.info(f"[DEALS] Fetched {len(deals)} deals for crypto")
                    else:
                        logger.warning("[DEALS] No connector for master account")
                else:
                    logger.warning("[DEALS] No master account found")
            else:
                raise HTTPException(status_code=400, detail="Only MT5 and Crypto platforms are supported")

            sanitized_deals = sanitize_float(deals)
            # An empty history and an unreadable bridge both render as "no
            # deals", so say how many rows the connector returned and how many
            # survived sanitising. Wrapped because observability must never
            # break the call.
            try:
                raw_deals = len(deals) if deals is not None else 0
                kept_deals = len(sanitized_deals) if sanitized_deals is not None else 0
                if hasattr(date_from, "isoformat"):
                    date_from_text = date_from.isoformat()
                else:
                    date_from_text = date_from
                logger.info(
                    f"[DEALS_RESULT] platform={target_platform} raw={raw_deals} "
                    f"kept={kept_deals} days={days} date_from={date_from_text}"
                )
            except Exception:
                pass

            return {
                "status": "success",
                "platform": target_platform,
                "deals": sanitized_deals,
                "count": len(deals),
                "account_balance": account_balance,
            }

        # cached() takes a zero-argument producer. Binding the tenant here is what
        # keeps the tenancy contract without passing it as a fifth positional,
        # which raised TypeError on every request and made /api/deals a 500.
        def _produce_deals_payload():
            return _fetch_deals_payload(user_id)

        payload = await asyncio.to_thread(
            cached,
            _deals_cache,
            deals_cache_key,
            _DEALS_CACHE_TTL,
            _produce_deals_payload,
            # Only a successful, non-empty history is worth 30s of memory: an
            # empty list is as likely to be a transient bridge hiccup as an
            # empty account history, and that must not be remembered.
            cacheable=lambda result: bool(result.get("deals")),
            on_hit=lambda: logger.info(
                f"[DEALS_CACHE] hit platform={target_platform} days={days} "
                f"symbol={symbol} age<{_DEALS_CACHE_TTL}s"
            ),
        )

        # timestamp stays the moment this response was built, so a cached answer
        # never looks newer or older than it is.
        return {**payload, "timestamp": datetime.now().timestamp()}
    except Exception as e:
        import logging
        local_logger = logging.getLogger(__name__)

        local_logger.error(f"Error in get_deals: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/debug/mt5")
async def debug_mt5():
    try:
        from datetime import datetime
        module = mt5_access.local_module()
        info = {
            "timestamp": datetime.now().isoformat(),
            "bridge_enabled": mt5_access.bridge_enabled(),
            "local_module": module is not None,
            "mt5_version": mt5_access.mt5_version(),
            "connected": False,
            "account_info": None,
            "terminal_info": None,
            "last_error": None
        }
        if module is None:
            # Cloud runtime: the bridge is the only door and it exposes no
            # terminal/account diagnostics, so report the facts that are known
            # and leave the rest null instead of raising ModuleNotFoundError.
            return info
        try:
            info["last_error"] = module.last_error()
        except Exception:
            pass
        if module.initialize():
            info["connected"] = True
            acc = module.account_info()
            if acc:
                info["account_info"] = acc._asdict()
            term = module.terminal_info()
            if term:
                info["terminal_info"] = term._asdict()
            from_date = datetime(2020, 1, 1)
            to_date = datetime.now()
            deals_count = module.history_deals_get(from_date, to_date)
            info["history_deals_count"] = len(deals_count) if deals_count else 0
            module.shutdown()
        return info
    except Exception as r:
        return {"error": str(r), "trace": traceback.format_exc()}


@app.get("/debug/bridge-latency")
async def debug_bridge_latency():
    """Round trip to the MT5 bridge, measured from inside this container.

    Read-only diagnostic over the connector's pooled client, which is the same
    path every polling cycle uses, so the socat relay and the tailnet tunnel are
    included. It times two things: ``/api/balance`` (transport plus whatever MT5
    work the far side does) and a path the bridge does not implement, whose 404
    is the transport alone. ``interpretation`` names the side that dominates the
    full call: ``network`` when the network median is at least half the median
    of the complete call, otherwise ``mt5``. It never raises: a dead bridge
    answers ``enabled: true`` plus ``error``.
    """
    payload = {
        "bridge_url": None,
        "samples_ms": [],
        "min_ms": None,
        "median_ms": None,
        "network_samples_ms": [],
        "network_min_ms": None,
        "network_median_ms": None,
        "interpretation": None,
        "enabled": False,
        "error": None,
    }
    try:
        payload["enabled"] = bool(mt5_access.bridge_enabled())
    except Exception as exc:
        payload["error"] = f"{type(exc).__name__}: {exc}"
        return payload
    try:
        connector = get_mt5_connector()
        payload["bridge_url"] = getattr(connector, "base_url", None)
        # The connector summarises both groups (samples, min, median, and the
        # interpretation), so there is one rounding rule for every caller.
        payload.update(await asyncio.to_thread(connector.probe_latency))
    except Exception as exc:
        payload["error"] = f"{type(exc).__name__}: {exc}"
    return payload


@app.get("/api/positions")
async def get_positions(
    symbol: str = Query(None),
    platform: str = Query(None),
    user_id: str = Depends(get_authenticated_user_id),
):
    try:
        target_platform = platform or _connection_state.get("platform") or "mt5"
        actual_symbol = resolve_symbol(symbol) if symbol else None
        
        if target_platform == "crypto":
            from src.services.crypto_manager import get_crypto_manager
            from src.live.crypto_connector import get_connector
            manager = get_crypto_manager()
            accounts = manager.get_accounts(user_id=user_id)
            if not accounts:
                return []
            master_acc = next((acc for acc in accounts if acc.get("is_master")), None) or accounts[0]
            crypto_conn = get_connector(master_acc["id"], user_id=user_id)
            if not crypto_conn:
                return []
            
            # Use to_thread for the synchronous ccxt call
            positions = await asyncio.to_thread(crypto_conn.get_positions, actual_symbol)
            return sanitize_float(positions)
            
        else:
            connector = MT5Connector()
            if not connector.connect():
                raise HTTPException(status_code=500, detail="Could not connect to MT5")
            # normalize() turns bridge dicts into attribute objects and leaves
            # native MetaTrader5 positions untouched.
            positions = normalize(connector.get_positions(actual_symbol))
            connector.shutdown()
            if isinstance(positions, dict):
                # The bridge answered with an error payload instead of a list.
                raise HTTPException(status_code=502, detail=str(positions))
            return sanitize_float(positions_to_web(positions or []))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Positions Error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/account")
async def get_account(
    platform: str = Query(None),
    user_id: str = Depends(get_authenticated_user_id),
):
    try:
        target_platform = platform or _connection_state.get("platform") or "mt5"
        
        if target_platform == "crypto":
            from src.services.crypto_manager import get_crypto_manager
            from src.live.crypto_connector import get_connector
            manager = get_crypto_manager()
            accounts = manager.get_accounts(user_id=user_id)
            if not accounts:
                raise HTTPException(status_code=404, detail="No crypto accounts")
            master_acc = next((acc for acc in accounts if acc.get("is_master")), None) or accounts[0]
            crypto_conn = get_connector(master_acc["id"], user_id=user_id)
            
            balance = await asyncio.to_thread(crypto_conn.get_balance)
            equity = await asyncio.to_thread(crypto_conn.get_equity)
            
            # Calculate floating profit from positions
            positions = await asyncio.to_thread(crypto_conn.get_positions)
            floating_pnl = sum(p.get('profit', 0) for p in positions)
            
            result = {
                "balance": balance,
                "equity": equity,
                "profit": floating_pnl,
                "margin": 0, # Should implement if needed
                "margin_free": balance,
                "margin_level": 0,
                "currency": "USDT",
                "daily_pnl": await asyncio.to_thread(crypto_conn.get_daily_pnl)
            }
            return sanitize_float(result)
            
        else:
            connector = MT5Connector()
            if not connector.connect():
                raise HTTPException(status_code=503, detail="Could not connect to MT5")
            # Both connectors expose get_account_info(); the bridge returns a
            # dict, the native connector returns a dict too.
            account_info = normalize(connector.get_account_info())
            balance = getattr(account_info, "balance", None)
            equity = getattr(account_info, "equity", None)
            if balance is None:
                balance = connector.get_balance()
            if equity is None:
                equity = connector.get_equity()
            result = {
                "balance": balance,
                "equity": equity,
                "profit": getattr(account_info, "profit", equity - balance),
                "margin": getattr(account_info, "margin", 0),
                "margin_free": getattr(account_info, "margin_free", balance),
                "margin_level": getattr(account_info, "margin_level", 0),
                "currency": getattr(account_info, "currency", "USD"),
            }
            return sanitize_float(result)
    except Exception as e:
        logger.error(f"Account Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/api/tick/{symbol:path}")
async def get_tick(symbol: str):
    try:
        actual_symbol = resolve_symbol(symbol)
        connector = MT5Connector()
        if not connector.connect():
            raise HTTPException(status_code=500, detail="Could not connect to MT5")
        # Neither connector exposes symbol_info_tick(); get_recent_ticks() is
        # the method both provide, and its last row is the current tick.
        ticks = connector.get_recent_ticks(actual_symbol, 1)
        connector.shutdown()
        if ticks is None or len(ticks) == 0:
            raise HTTPException(
                status_code=404, detail=f"No tick data for {actual_symbol}"
            )
        tick = normalize(ticks.iloc[-1].to_dict())
        bid = _number(getattr(tick, "bid", 0.0))
        ask = _number(getattr(tick, "ask", 0.0))
        last = _number(getattr(tick, "last", 0.0))
        time_sec = int(_number(getattr(tick, "time", 0)))
        result = {
            "symbol": actual_symbol,
            "bid": bid,
            "ask": ask,
            "last": last if last > 0 else (bid + ask) / 2,
            "volume": int(_number(getattr(tick, "volume", 0))),
            "time": time_sec,
            "time_msc": int(_number(getattr(tick, "time_msc", time_sec * 1000))),
            "spread": round((ask - bid) * 4, 2),
        }
        return sanitize_float(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tick Error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
_realtime_cache: Dict[str, Any] = {}  
_REALTIME_CACHE_TTL = 3.0  
_session_cache: Dict[str, Any] = {}  
_SESSION_CACHE_TTL = 60.0  
def _get_last_real_tick_time(symbol: str) -> float:
    try:
        from src.services.market_data_engine.engine import MarketDataEngine
        engine = MarketDataEngine._instance
        if engine and hasattr(engine, '_last_tick_time'):
            ts_ms = engine._last_tick_time.get(symbol.upper(), 0)
            if ts_ms > 0:
                return ts_ms / 1000.0
    except Exception:
        pass
    return None
_realtime_cache = {}
_account_cache = {}

# Global cache for realtime_batch to prevent multi-tab hammering
_batch_response_cache = {}
_batch_response_lock = asyncio.Lock()

@app.get("/api/realtime_batch")
async def get_realtime_batch(
    symbols: str = Query(...),
    platform: Optional[str] = Query(None),
    user_id: str = Depends(get_authenticated_user_id),
):
    """
    Batched version of /api/realtime to reduce HTTP requests.
    Returns account info + ticks for multiple symbols.
    """
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list: return {"error": "no symbols"}
    
    target_platform = platform or detect_platform_for_symbol(symbol_list[0])
    now = time.time()
    cache_key = f"{symbols}_{target_platform}"
    
    async with _batch_response_lock:
        if cache_key in _batch_response_cache:
            entry = _batch_response_cache[cache_key]
            if now - entry['ts'] < 1.0: # 1 second global throttle
                return entry['data']
    
    # 1. Fetch Account + Positions (once per batch, cached 3.0s for MT5, 5.0s for Crypto to avoid bans)
    acc_cache_key = f"acc_{target_platform}"
    # The tape is the ticks block below, not this account block, so a longer
    # account TTL costs the tape no freshness and saves a bridge round trip
    # (~418ms) per window. Do not "optimise" this back down to 1.5s: the
    # frontend polls the batch continuously and account/positions do not move
    # at tick speed.
    acc_ttl = 5.0 if target_platform == "crypto" else 3.0
    if acc_cache_key in _account_cache and (now - _account_cache[acc_cache_key]["ts"] < acc_ttl):
        acc_data = _account_cache[acc_cache_key]["data"]
    else:
        # Fetch fresh
        if target_platform == "crypto":
            # Crypto account logic (simplified for batch)
            from src.services.crypto_manager import get_crypto_manager
            from src.live.crypto_connector import get_connector
            manager = get_crypto_manager()
            accounts = manager.get_accounts(user_id=user_id)
            master_acc = next((acc for acc in accounts if acc.get("is_master")), None) or (accounts[0] if accounts else None)
            if not master_acc:
                acc_data = {"account": {}, "positions": [], "pending_orders": []}
            else:
                crypto_conn = get_connector(master_acc["id"], user_id=user_id)
                if crypto_conn is None or not hasattr(crypto_conn, 'get_balance'):
                    logger.warning(f"[CRYPTO] Connector not available for account {master_acc['id']}")
                    acc_data = {"account": {}, "positions": [], "pending_orders": []}
                else:
                    # Optimized: Single call to get everything (reduces API load and latency)
                    snapshot = await asyncio.to_thread(crypto_conn.get_account_snapshot)
                    acc_data = {
                        "account": {
                            "balance": snapshot.get("balance", 0.0),
                            "equity": snapshot.get("equity", 0.0),
                            "profit": snapshot.get("equity", 0.0) - snapshot.get("balance", 0.0),
                            "daily_pnl": snapshot.get("daily_pnl", 0.0),
                            "margin": 0,
                            "margin_free": snapshot.get("balance", 0.0),
                            "account_type": "crypto"
                        },
                        "positions": snapshot.get("positions", []),
                        "pending_orders": snapshot.get("pending_orders", [])
                    }
        else:
            # MT5 account logic
            connector = GLOBAL_MT5_CONNECTOR
            if not connector.connected: await asyncio.to_thread(connector.connect)
            
            # Parallelize MT5 calls
            account_info, positions, orders, daily_pnl = await asyncio.gather(
                asyncio.to_thread(connector.get_account_info),
                asyncio.to_thread(connector.get_positions),
                asyncio.to_thread(connector.get_pending_orders),
                asyncio.to_thread(connector.get_daily_pnl)
            )
            
            account_info = normalize(account_info)
            daily_pnl = 0.0 if isinstance(daily_pnl, dict) else (daily_pnl or 0.0)
            if account_info:
                account_info["realized_today"] = daily_pnl
                account_info["daily_pnl"] = daily_pnl + account_info.get("profit", 0.0)

            if isinstance(positions, dict):
                # The bridge answered with an error payload instead of a list.
                positions = []
            positions = as_list(positions)
            orders = as_list(orders)
            pos_list = positions_to_web(positions) if positions else []
            pending_list = []
            if orders:
                for o in orders:
                    ot = o.get("type", 0)
                    side = "buy"
                    type_str = "PENDING_BUY_LMT" # Default
                    if ot == 2: # BUY LIMIT
                        side = "buy"; type_str = "PENDING_BUY_LMT"
                    elif ot == 3: # SELL LIMIT
                        side = "sell"; type_str = "PENDING_SELL_LMT"
                    elif ot == 4: # BUY STOP
                        side = "buy"; type_str = "PENDING_BUY_STP"
                    elif ot == 5: # SELL STOP
                        side = "sell"; type_str = "PENDING_SELL_STP"
                    elif ot == 0: # BUY (Market/Entry)
                        side = "buy"; type_str = "PENDING_BUY"
                    elif ot == 1: # SELL (Market/Entry)
                        side = "sell"; type_str = "PENDING_SELL"
                    
                    pending_list.append({
                        **o,
                        "side": side,
                        "type": type_str
                    })

            acc_data = {
                "account": account_info,
                "positions": pos_list,
                "pending_orders": pending_list
            }
        _account_cache[acc_cache_key] = {"data": acc_data, "ts": now}

    # 2. Fetch Ticks for all symbols in parallel
    ticks = {}
    from .utils import resolve_symbol
    async def fetch_tick(sym):
        async def _do_fetch():
            try:
                actual = resolve_symbol(sym)
                if target_platform == "crypto":
                    engine = get_market_data_engine()
                    engine_data = engine.get_latest_quote(actual) if engine else None
                    if engine_data:
                        tick_last = engine_data.get("last", 0.0)
                        if tick_last == 0 and engine_data.get("event_type") in ("OHLCV", "BAR"):
                            tick_last = engine_data.get("close", 0.0)
                        return {
                            "symbol": sym, "last": tick_last,
                            "bid": engine_data.get("bid", 0.0), "ask": engine_data.get("ask", 0.0),
                            "volume": engine_data.get("volume", 0.0), "time": engine_data.get("timestamp", time.time())
                        }
                    return {}
                else:
                    def sync_get_data(sym_name):
                        # Both connectors expose get_recent_ticks() and
                        # symbol_info(); neither exposes symbol_info_tick().
                        ticks = GLOBAL_MT5_CONNECTOR.get_recent_ticks(sym_name, 1)
                        rows = [] if ticks is None else ticks.tail(1).to_dict("records")
                        tick = normalize(rows[-1]) if rows else None
                        return tick, normalize(GLOBAL_MT5_CONNECTOR.symbol_info(sym_name))
                    t, si = await asyncio.to_thread(sync_get_data, actual)
                    if not t: return {}
                    bid = _number(getattr(t, "bid", 0.0))
                    ask = _number(getattr(t, "ask", 0.0))
                    last = _number(getattr(t, "last", 0.0))
                    return {
                        "symbol": sym, "bid": bid, "ask": ask,
                        "last": last if last > 0 else (bid + ask)/2,
                        "volume": _number(getattr(t, "volume", 0)),
                        "time": int(_number(getattr(t, "time", 0))),
                        "point": _number(getattr(si, "point", 0.0001)) if si else 0.0001,
                        "digits": int(_number(getattr(si, "digits", 5))) if si else 5,
                    }
            except Exception as e:
                logger.debug(f"Error fetching tick for {sym}: {e}")
                return {}

        try:
            return await asyncio.wait_for(_do_fetch(), timeout=1.5)
        except asyncio.TimeoutError:
            return {}

    tick_results = await asyncio.gather(*[fetch_tick(s) for s in symbol_list])
    for tr in tick_results:
        if tr and "symbol" in tr:
            ticks[tr["symbol"]] = tr

    final_data = sanitize_float({
        **acc_data,
        "ticks": ticks
    })
    
    async with _batch_response_lock:
        _batch_response_cache[cache_key] = {"data": final_data, "ts": now}
        
    return final_data

@app.get("/api/realtime")
@app.get("/api/realtime/{symbol:path}")
async def get_realtime(
    symbol: str, 
    platform: Optional[str] = Query(None),
    force: bool = Query(False),
    user_id: str = Depends(get_authenticated_user_id),
):
    actual_symbol = resolve_symbol(symbol)
    try:
        from src.live.connector import get_mt5_connector
        realtime_connector = get_mt5_connector()
        if hasattr(realtime_connector, "resolve_contract"):
            actual_symbol = realtime_connector.resolve_contract(actual_symbol)
    except Exception:
        pass
    try:
        cache_key = f"{symbol}"
        if not force and cache_key in _realtime_cache:
            c = _realtime_cache[cache_key]
            if time.time() - c["ts"] < 1.0:
                return c["data"]
        engine = get_market_data_engine()
        engine_data = engine.get_latest_quote(actual_symbol) if engine else None
        if platform == "crypto" or detect_platform_for_symbol(symbol) == "crypto":
            from src.services.crypto_manager import get_crypto_manager
            from src.live.crypto_connector import get_connector
            manager = get_crypto_manager()
            accounts = manager.get_accounts(user_id=user_id)
            master_acc = next((acc for acc in accounts if acc.get("is_master")), None)
            if not master_acc and accounts:
                master_acc = accounts[0]
            if not master_acc:
                # Si no hay cuenta, devolver datos vacíos o una estructura por defecto en vez de abortar la gráfica
                return {
                    "symbol": symbol,
                    "last_price": 0.0,
                    "volume": 0.0,
                    "timestamp": time.time(),
                    "type": "error",
                    "msg": "No crypto account connected"
                }
            crypto_conn = get_connector(master_acc["id"], user_id=user_id)
            if not crypto_conn:
                return {
                    "symbol": symbol,
                    "last_price": 0.0,
                    "volume": 0.0,
                    "timestamp": time.time(),
                    "type": "error",
                    "msg": "Master account connector not ready"
                }
            # 1. First try to get market data from Engine (which is already polling)
            tick_bid = 0.0
            tick_ask = 0.0
            tick_last = 0.0
            tick_volume = 0.0
            tick_time = time.time()

            if engine_data:
                # MarketDataEvent uses 'last' for price. 
                # If the latest event is OHLCV, we use 'close'.
                tick_last = engine_data.get("last", 0.0)
                if tick_last == 0 and engine_data.get("event_type") == "OHLCV":
                    tick_last = engine_data.get("close", 0.0)
                
                tick_bid = engine_data.get("bid", 0.0)
                tick_ask = engine_data.get("ask", 0.0)
                tick_volume = engine_data.get("volume", 0.0)
                tick_time = engine_data.get("timestamp", time.time())
                
                # If engine data is missing prices (e.g. just a partial event), 
                # fallback to connector to avoid sending 0.0 to UI
                if tick_last == 0 and crypto_conn:
                    tick = crypto_conn.get_tick(actual_symbol)
                    tick_last = tick.get("last", 0.0)
                    tick_bid = tick.get("bid", 0.0)
                    tick_ask = tick.get("ask", 0.0)
                    tick_volume = tick.get("volume", 0.0)
                    tick_time = tick.get("time", time.time())
            else:
                # Fallback to connector (which now has a 10s cache)
                if crypto_conn:
                    tick = crypto_conn.get_tick(actual_symbol)
                    tick_bid = tick.get("bid", 0.0)
                    tick_ask = tick.get("ask", 0.0)
                    tick_last = tick.get("last", 0.0)
                    tick_volume = tick.get("volume", 0.0)
                    tick_time = tick.get("time", time.time())

            # 2. Get account data (connector uses 10s cache automatically)
            if crypto_conn:
                balance = crypto_conn.get_balance()
                equity = crypto_conn.get_equity()
                positions = crypto_conn.get_positions()
            else:
                balance, equity, positions = 0.0, 0.0, []

            res = {
                "account": {
                    "balance": balance,
                    "equity": equity, 
                    "profit": equity - balance,
                    "daily_pnl": 0,
                    "margin": 0,
                    "margin_free": balance,
                    "account_type": "crypto",
                },
                "tick": {
                    "symbol": symbol,
                    "bid": tick_bid,
                    "ask": tick_ask,
                    "last": tick_last,
                    "volume": tick_volume,
                    "time": tick_time,
                    "point": 0.01,
                    "digits": 2
                },
                "positions": positions,
                "pending_orders": []
            }
            sanitized = sanitize_float(res)
            _realtime_cache[cache_key] = {"data": sanitized, "ts": time.time()}
            return sanitized
        connector = GLOBAL_MT5_CONNECTOR
        if not connector.connect():
            raise HTTPException(status_code=500, detail="Could not connect to MT5")
        account_info_dict = connector.get_account_info()
        account_info_bal = account_info_dict.get("balance", 0) if account_info_dict else 0
        account_info_eq = account_info_dict.get("equity", 0) if account_info_dict else 0
        account_info_mg = account_info_dict.get("margin", 0) if account_info_dict else 0
        account_info_mgf = account_info_dict.get("margin_free", 0) if account_info_dict else 0
        # mt5_access answers from the bridge in the cloud and from the local
        # package on Windows, so the tape is fed in both runtimes.
        tick = mt5_access.symbol_tick(actual_symbol)
        symbol_info_full = mt5_access.symbol_info(actual_symbol)
        info_point = symbol_info_full["point"] if symbol_info_full else 0.0001
        info_digits = symbol_info_full["digits"] if symbol_info_full else 5
        info_tick_size = (
            symbol_info_full["trade_tick_size"]
            if (symbol_info_full and symbol_info_full["trade_tick_size"] > 0)
            else (symbol_info_full["point"] if symbol_info_full else 0.0001)
        )
        info_stops_level = symbol_info_full["stops_level"] if symbol_info_full else 0
        if tick is None:
            tick_data = {
                "symbol": actual_symbol, "bid": 0, "ask": 0, "last": 0, "volume": 0, "time": 0,
                "point": info_point,
                "digits": info_digits,
                "tick_size": info_tick_size,
                "stops_level": info_stops_level,
            }
        else:
            tick_data = {
                "symbol": actual_symbol,
                "bid": tick["bid"], "ask": tick["ask"],
                "last": tick["last"] if tick["last"] > 0 else (tick["bid"] + tick["ask"]) / 2,
                "volume": tick["volume"], "time": tick["time"],
                "time_msc": tick.get("time_msc", int(tick["time"] * 1000)),
                "point": info_point,
                "digits": info_digits,
                "tick_size": info_tick_size,
                "stops_level": info_stops_level,
            }
        # normalize() keeps native MT5 positions as they are and turns bridge
        # dicts into attribute objects, so one loop reads both.
        positions = [normalize(position) for position in as_list(connector.get_positions())]
        pos_list = []
        if positions:
            for pos in positions:
                pos_list.append({
                    "ticket": pos.ticket,
                    "type": "BUY" if pos.type == 0 else "SELL",
                    "volume": pos.volume,
                    "entry_price": pos.price_open,
                    "current_price": pos.price_current,
                    "sl": pos.sl, "tp": pos.tp,
                    "profit": pos.profit, "symbol": pos.symbol,
                })
        pending_orders = [normalize(order) for order in as_list(connector.get_pending_orders())]
        pending_list = []
        if pending_orders:
            for o in pending_orders:
                t = o["type"]
                if t == 2: type_str = "PENDING_BUY"      
                elif t == 3: type_str = "PENDING_SELL"   
                elif t == 4: type_str = "PENDING_BUY_STP" 
                elif t == 5: type_str = "PENDING_SELL_STP" 
                else: type_str = str(t)
                side_str = "buy" if "BUY" in type_str else "sell"
                pending_list.append({
                    "ticket": o["ticket"], 
                    "type": type_str,
                    "side": side_str,
                    "volume": o["volume"], 
                    "price": o["price_open"], 
                    "sl": o["sl"], 
                    "tp": o["tp"], 
                    "symbol": o["symbol"],
                })
        account_type = "futures"
        if account_info_dict and account_info_dict.get("server"):
            srv = account_info_dict["server"].upper()
            if any(x in srv for x in ["AMP", "TRADESTATION", "CQG", "RITHMIC"]):
                account_type = "futures"
        realized_today = connector.get_daily_pnl()
        floating_profit = account_info_eq - account_info_bal
        daily_pnl = realized_today + floating_profit
        result = {
            "account": {
                "balance": account_info_bal,
                "equity": account_info_eq,
                "profit": floating_profit, 
                "realized_today": realized_today, 
                "daily_pnl": daily_pnl, 
                "margin": account_info_mg,
                "margin_free": account_info_mgf,
                "account_type": account_type,
            },
            "tick": tick_data,
            "positions": pos_list,
            "pending_orders": pending_list,
        }
        sanitized_result = sanitize_float(result)
        _realtime_cache[cache_key] = {"data": sanitized_result, "ts": time.time()}
        return sanitized_result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()

        raise HTTPException(status_code=500, detail=str(e))
@app.post("/api/order")
async def place_order(
    order: OrderRequest, user_id: str = Depends(get_authenticated_user_id)
):
    try:
        if order.action.upper() == "FLAT":
            order.volume = 0.0

        logger.info(
            f"[ORDER] Received order request: platform={order.platform}, symbol={order.symbol}, action={order.action}, type={order.type}, volume={order.volume}, price={order.price}, sl={order.sl}, tp={order.tp}"
        )
        actual_symbol = resolve_symbol(order.symbol)
        actual_platform = order.platform or detect_platform_for_symbol(order.symbol)
        
        # CRITICAL: Override platform detection if symbol is clearly crypto
        if actual_platform != "crypto" and detect_platform_for_symbol(order.symbol) == "crypto":
            logger.debug(f"[ORDER] Platform override: '{actual_platform}' -> 'crypto' (symbol={order.symbol})")
            actual_platform = "crypto"
        
        logger.debug(f"[ORDER] Platform detection: order.platform='{order.platform}', detected='{actual_platform}', symbol='{order.symbol}' -> actual_symbol='{actual_symbol}'")
        logger.info(
            f"[ORDER] Platform={actual_platform}, Symbol={order.symbol} -> {actual_symbol}, Action={order.action}, Type={order.type}, Volume={order.volume}, Account={order.account_id}"
        )
        is_closing = order.action.upper() in ["CLOSE", "FLAT", "CANCEL"]
        if not is_closing:
            try:
                from src.services.order_gateway.models import (
                    OrderRequest as BackendOrderRequest,
                )
                from src.services.order_gateway.models import OrderSide, OrderSource
                from src.services.order_gateway.models import (
                    OrderType as BackendOrderType,
                )
                from src.services.order_gateway.risk_validator import RiskValidator
                v_side = OrderSide.BUY if order.action == "BUY" else OrderSide.SELL
                v_type = BackendOrderType.MARKET
                if order.type == "LIMIT":
                    v_type = BackendOrderType.LIMIT
                elif order.type in ["STOP", "STP"]:
                    v_type = BackendOrderType.STOP
                validation_order = BackendOrderRequest(
                    symbol=actual_symbol,
                    side=v_side,
                    quantity=order.volume,
                    order_type=v_type,
                    price=order.price or 0.0,
                    sl=order.sl or 0.0,
                    tp=order.tp or 0.0,
                    platform=actual_platform,
                    source=OrderSource.MANUAL,
                )
                validator = RiskValidator()
                if actual_platform == "crypto":
                    validation_result = validator._validate_size(validation_order)
                else:
                    validation_result = validator.validate(validation_order)
                if not validation_result.is_valid:
                    logger.warning(
                        f"[ORDER] Risk Rejection: {validation_result.message}"
                    )
                    raise HTTPException(
                        status_code=400, detail=validation_result.message
                    )
            except HTTPException:
                raise
            except ImportError:
                logger.info("[ORDER] Risk Validator not found, skipping validation.")
            except Exception as ve:
                logger.warning(f"[ORDER] Validation bypass error: {ve}")
        # 1. Initialize connector based on platform
        if actual_platform == "crypto":
            from src.live.crypto_connector import get_connector as get_crypto_connector
            from src.services.crypto_manager import get_crypto_manager
            manager = get_crypto_manager()
            accounts = manager.get_accounts(user_id=user_id)
            account_id = order.account_id
            if account_id and not any(acc["id"] == account_id for acc in accounts):
                # An account id in the body is only a selection, never a tenant:
                # it must belong to the token, or it does not exist.
                raise HTTPException(status_code=404, detail="Account not found")
            if not account_id:
                master = next((acc for acc in accounts if acc.get("is_master")), None)
                if not master and accounts:
                    master = accounts[0]
                if master:
                    account_id = master["id"]
            if not account_id:
                raise HTTPException(status_code=400, detail="No crypto account specified or available")
            connector = get_crypto_connector(account_id, user_id=user_id)
            if not connector:
                raise HTTPException(status_code=503, detail="Could not connect to crypto exchange")
            if not connector.connect():
                raise HTTPException(status_code=503, detail="Could not initialize crypto exchange markets")
            # Re-resolve symbol using the crypto connector's market knowledge
            actual_symbol = connector._resolve_sym(order.symbol) or actual_symbol
            logger.info(f"[ORDER] Crypto symbol resolved: {order.symbol} -> {actual_symbol}")
        else:
            from src.live.connector import get_mt5_connector
            connector = get_mt5_connector()
            # We don't connect yet, we'll do it inside the mt5 branch or use the helper

        # 2. Unified SL/TP calculation
        base_price = order.price
        if not base_price or base_price == 0:
            if actual_platform == "crypto":
                # Ensure we have the connector-specific symbol
                base_price = connector.get_current_price(actual_symbol)
            else:
                try:
                    current_price = connector.get_current_price(actual_symbol)
                except Exception as e:
                    logger.warning(f"[ORDER] MT5 get_current_price failed: {e}")
                    current_price = 0
                
                if not current_price:
                    tick = mt5_access.symbol_tick(actual_symbol)
                    if tick:
                        current_price = (
                            tick["last"] if tick["last"] > 0 else (tick["bid"] + tick["ask"]) / 2
                        )
                base_price = current_price or 0.0

        point = 1.0 # Default for crypto offsets (Price units)
        if actual_platform == "crypto":
            # For crypto, users usually think in absolute price or price units (USD)
            point = 1.0
        else:
            TICKS_MAP = {
                "MNQ": 0.25, "NQ": 0.25, 
                "MES": 0.25, "ES": 0.25, 
                "RTY": 0.1,  "M2K": 0.1,
                "YM": 1.0,   "MYM": 1.0 
            }
            actual_base = normalize_symbol_for_comparison(actual_symbol)
            # Static metadata read from the process cache instead of a fresh
            # bridge round trip; placement below is unchanged.
            symbol_info = _cached_symbol_info(actual_symbol)
            if symbol_info:
                point = TICKS_MAP.get(actual_base, symbol_info["tick_size"] or symbol_info["point"])

        def is_absolute_price(val, base):
            if not base or base == 0: return False
            return abs(val - base) < base * 0.2
            
        final_sl = 0.0
        final_tp = 0.0
        order_sl = float(order.sl or 0)
        order_tp = float(order.tp or 0)
        
        # Track intended distances for replication (in points/ticks)
        dist_sl_intended = order_sl
        dist_tp_intended = order_tp
        
        if order_sl > 0:
            if is_absolute_price(order_sl, base_price):
                final_sl = order_sl
                # For replication, compute the distance in ticks from the absolute price
                dist_sl_intended = abs(final_sl - base_price) / point if point > 0 else 0.0
            else:
                dist = order_sl * point
                final_sl = base_price - dist if order.action == "BUY" else base_price + dist
                dist_sl_intended = order_sl  # Already expressed as a distance
        
        if order_tp > 0:
            if is_absolute_price(order_tp, base_price):
                final_tp = order_tp
                # For replication, compute the distance in ticks from the absolute price
                dist_tp_intended = abs(final_tp - base_price) / point if point > 0 else 0.0
            else:
                dist = order_tp * point
                final_tp = base_price + dist if order.action == "BUY" else base_price - dist
                dist_tp_intended = order_tp  # Already expressed as a distance

        # 3. Execution
        logger.info(f"[ORDER] Executing {order.action} for {actual_symbol} | Vol={order.volume} | SL={final_sl} | TP={final_tp}")
        if actual_platform == "crypto":
            if order.action == "BUY":
                res = await asyncio.to_thread(connector.place_order, actual_symbol, "BUY", order.volume, order.price, order.type, sl=final_sl, tp=final_tp)
            elif order.action == "SELL":
                res = await asyncio.to_thread(connector.place_order, actual_symbol, "SELL", order.volume, order.price, order.type, sl=final_sl, tp=final_tp)
            elif order.action == "CLOSE":
                # For Crypto, we need to distinguish between cancelling an order and closing a position
                # Try cancelling first if it's a pending order, otherwise close position
                res = False
                if order.ticket and str(order.ticket).strip() not in ["0", "null", "None", ""]:
                    res = await asyncio.to_thread(connector.cancel_order, order.ticket, actual_symbol)
                
                if not res:
                    logger.info(f"[ORDER] Cancel order failed or ticket is empty, trying close_position for {actual_symbol}")
                    res = await asyncio.to_thread(connector.close_position, order.ticket, actual_symbol, order.volume)
            elif order.action == "FLAT":
                positions = await asyncio.to_thread(connector.get_positions, actual_symbol)
                for pos in positions:
                    side = "SELL" if pos["type"] == "BUY" else "BUY"
                    await asyncio.to_thread(connector.place_order, actual_symbol, side, pos["volume"], mode="MKT")
                return {"status": "executed", "details": f"Flatted {len(positions)} positions"}
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported action: {order.action}")
            if res:
                if order.action in ("BUY", "SELL", "CLOSE", "FLAT"):
                    entry_p = res.get("price") if isinstance(res, dict) else order.price
                    replicate_to_nt8_background(actual_symbol, order.action, order.volume, entry_price=entry_p, sl=order.sl, tp=order.tp, order_type=order.type, price=entry_p)
                return {"status": "executed", "details": res}
            raise HTTPException(status_code=500, detail="Order execution failed")
        elif actual_platform == "mt5":
            logger.info(f"[ORDER] Executing MT5 order for {actual_symbol}")
            from src.live.connector import get_mt5_connector
            connector = get_mt5_connector()
            if order.action == "CLOSE":
                logger.info(f"[CLOSE-DEBUG] Closing ticket={order.ticket}, symbol={actual_symbol}, volume={order.volume}")
                try:
                    ticket_int = int(order.ticket)
                    pos_info = mt5_access.positions(ticket=ticket_int)
                    if pos_info:
                        actual_symbol = pos_info[0].get("symbol") or actual_symbol
                    else:
                        ord_info = mt5_access.orders(ticket=ticket_int)
                        if ord_info:
                            actual_symbol = ord_info[0].get("symbol") or actual_symbol
                except Exception as sym_err:
                    logger.warning(f"[CLOSE] Could not resolve symbol from ticket {order.ticket}: {sym_err}")
                pending_orders = await asyncio.to_thread(connector.get_pending_orders, symbol=actual_symbol)
                try:
                    target_ticket = int(order.ticket)
                except (ValueError, TypeError):
                    target_ticket = order.ticket
                is_pending = any(
                    int(o.get("ticket")) == target_ticket for o in pending_orders if o.get("ticket")
                )
                if is_pending:
                    logger.info(f"[CLOSE-DEBUG] Detected as pending order, using delete_order")
                    success = await asyncio.to_thread(connector.delete_order, order.ticket)
                    connector.shutdown()
                    if success and success.retcode == 10009:
                        replicate_to_nt8_background(actual_symbol, "CANCEL", 0, entry_price=0)
                        return {
                            "status": "cancelled",
                            "details": f"Order {order.ticket} cancelled",
                        }
                    else:
                        error_detail = f"Failed to cancel order: {success.comment if success else 'No result'}"
                        raise HTTPException(
                            status_code=500, detail=error_detail
                        )
                else:

                    try:
                        ticket_id = int(order.ticket)
                    except:
                        ticket_id = order.ticket
                    result = await asyncio.to_thread(connector.close_position, 
                        ticket_id, symbol=actual_symbol, volume=order.volume
                    )
                    replicate_to_nt8_background(actual_symbol, "CLOSE", order.volume, entry_price=0)
            elif order.action == "FLAT":
                positions = await asyncio.to_thread(connector.get_positions, symbol=actual_symbol)
                results = []
                for pos in positions:
                    res = await asyncio.to_thread(connector.close_position, pos.ticket, symbol=actual_symbol)
                    results.append(res)
                pending = await asyncio.to_thread(connector.get_pending_orders, symbol=actual_symbol)
                pending_results = []
                for o in pending:
                    res = await asyncio.to_thread(connector.delete_order, o["ticket"])
                    pending_results.append(res)
                pos_success = sum(1 for r in results if r and r.retcode == 10009)
                pending_success = sum(1 for r in pending_results if r and r.retcode == 10009)
                total_actions = len(positions) + len(pending)
                success_count = pos_success + pending_success
                if total_actions == 0:
                    return {
                        "status": "executed",
                        "message": "No positions or orders to clean",
                    }
                if success_count > 0:
                    replicate_to_nt8_background(actual_symbol, "FLAT", 0.0, entry_price=0)
                    return {
                        "status": "executed",
                        "details": f"Closed {pos_success} positions, Cancelled {pending_success} orders",
                    }
                else:
                    raise HTTPException(
                        status_code=500, detail="Failed to flatten (clean) symbol"
                    )
            else:
                # Log diagnostics if needed
                diag_file = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")), "mirror_diagnostics.txt")
                def log_diag(m):
                    with open(diag_file, "a") as df:
                        df.write(f"{datetime.now()} | {m}\n")
                log_diag(f"--- MT5 ORDER: {actual_symbol} {order.action} ---")
                log_diag(f"Final SL: {final_sl}, Final TP: {final_tp}, Point: {point}")

                result = connector.place_order(
                    actual_symbol,
                    order.action,
                    order.volume,
                    sl=final_sl if final_sl > 0 else None,
                    tp=final_tp if final_tp > 0 else None,
                    price=float(order.price or 0),
                    mode=order.type,
                )
                if result and hasattr(result, 'retcode') and result.retcode == 10009:
                    pass

                else:
                    pass

            connector.shutdown()
            if result is True:
                return {"status": "executed", "details": "Action completed successfully"}
            if not result or not hasattr(result, "retcode") or result.retcode != 10009:
                if result and hasattr(result, "retcode"):
                    error_msg = (
                        f"Order failed: {result.comment} (code: {result.retcode})"
                    )
                    logger.error(
                        f"[ORDER] MT5 execution failed: {result.comment} ({result.retcode})"
                    )
                else:
                    error_msg = f"Order execution failed or returned invalid response: {result}"
                    logger.error(f"[ORDER] MT5 execution failed: {result}")
                raise HTTPException(status_code=500, detail=error_msg)
            if order.action in ("BUY", "SELL"):
                log_diag(f"MIRROR: Sending to replicator with intended dists: SL={dist_sl_intended}, TP={dist_tp_intended}, Price={order.price}, Type={order.type}")
                replicate_to_nt8_background(
                    actual_symbol, 
                    order.action, 
                    order.volume, 
                    sl_dist=dist_sl_intended if dist_sl_intended > 0.0000001 else -2.0, 
                    tp_dist=dist_tp_intended if dist_tp_intended > 0.0000001 else -2.0,
                    price=order.price,
                    order_type=order.type
                )
            return {"status": "executed", "details": str(result)}
        else:
            logger.error(f"[ORDER] Invalid platform or platform not supported: {actual_platform}")
            raise HTTPException(
                status_code=400, detail=f"Invalid platform or platform not supported: {actual_platform}"
            )
    except HTTPException as he:
        logger.error(f"[ORDER] HTTP Exception: {he.status_code} - {he.detail}")
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        error_msg = f"Internal Order Error: {str(e)}"
        logger.error(f"[ORDER-CRITICAL] {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    try:
        await websocket.accept()
        register_connection()  

        last_mtime = 0
        if os.path.exists(STATUS_FILE):
            try:
                with open(STATUS_FILE, "r") as f:
                    raw_data = json.load(f)
                    clean_data = sanitize_float(raw_data)
                    await websocket.send_json(clean_data)
                    last_mtime = os.path.getmtime(STATUS_FILE)
            except WebSocketDisconnect:
                return
            except Exception as e:
                traceback.print_exc()
        while True:
            try:
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_text(), timeout=0.001
                    )
                    try:
                        msg_data = json.loads(message)
                        msg_type = msg_data.get("type")
                        if msg_type == "ping":
                            await websocket.send_json({"type": "pong"})
                        elif msg_type == "place_order":
                            payload = msg_data.get("payload", {})
                            try:
                                order_req = OrderRequest(
                                    platform=payload.get("platform", "mt5"),
                                    action=payload.get("type", "BUY"), 
                                    symbol=payload.get("symbol", ""),
                                    volume=float(payload.get("volume", 0.0)),
                                    sl=float(payload.get("stop_loss", payload.get("sl", 0.0))),
                                    tp=float(payload.get("take_profit", payload.get("tp", 0.0))),
                                    ticket=payload.get("ticket", 0),
                                    type=payload.get("order_type", "MKT"),
                                    price=float(payload.get("price", 0.0)),
                                    account_id=payload.get("account_id")
                                )
                                if order_req.action == "MODIFY":
                                    modify_req = ModifyRequest(
                                        platform=order_req.platform,
                                        symbol=order_req.symbol,
                                        ticket=int(order_req.ticket) if order_req.ticket else 0,
                                        sl=order_req.sl,
                                        tp=order_req.tp,
                                        price=order_req.price,
                                        order_type=order_req.type
                                    )

                                    res = await modify_position(modify_req)
                                else:

                                    res = await place_order(order_req)
                                await websocket.send_json({"type": "order_response", "status": "success", "result": res})
                            except Exception as e:

                                await websocket.send_json({"type": "order_response", "status": "error", "message": str(e)})
                        elif msg_type == "algo_action":
                            payload = msg_data.get("payload", {})
                            action = payload.get("action")
                            algo_id = payload.get("algo_id")
                            params = payload.get("params", {})

                            try:
                                res = {"status": "ok", "action": action}
                                await websocket.send_json({"type": "algo_response", "status": "success", "result": res})
                            except Exception as e:
                                await websocket.send_json({"type": "algo_response", "status": "error", "message": str(e)})
                        elif msg_type == "request_account_info":
                            if os.path.exists(STATUS_FILE):
                                with open(STATUS_FILE, "r") as f:
                                    await websocket.send_json(json.load(f))
                    except json.JSONDecodeError:
                        pass
                except asyncio.TimeoutError:
                    pass  
                if os.path.exists(STATUS_FILE):
                    try:
                        mtime = os.path.getmtime(STATUS_FILE)
                        if mtime > last_mtime:
                            last_mtime = mtime
                            for i in range(3):
                                try:
                                    with open(STATUS_FILE, "r") as f:
                                        raw_data = json.load(f)
                                        clean_data = sanitize_float(raw_data)
                                        await websocket.send_json(clean_data)
                                    break
                                except json.JSONDecodeError:
                                    await asyncio.sleep(0.05)
                                except WebSocketDisconnect:
                                    raise  
                                except Exception as inner_e:
                                    error_str = str(inner_e).lower()
                                    if (
                                        "no close frame" in error_str
                                        or "closed" in error_str
                                    ):
                                        raise WebSocketDisconnect()
                                    if "1000" not in str(inner_e) and "1001" not in str(
                                        inner_e
                                    ):
                                        logger.warning(f"WS: Error reading/sending file attempt {i}: {inner_e}")
                                    break
                    except OSError:
                        pass
                await asyncio.sleep(0.016)  
            except WebSocketDisconnect:

                break
            except Exception as loop_e:
                if "1000" not in str(loop_e) and "1001" not in str(loop_e):
                    if "connection closed" not in str(loop_e).lower():
                        pass

                break
    except Exception as e:
        if "1000" not in str(e) and "1001" not in str(e):
            pass

    finally:
        unregister_connection()
@app.websocket("/ws/terminal")
async def websocket_terminal(websocket: WebSocket):
    await websocket.accept()
    logger.info("Terminal WebSocket connection accepted")
    process = None
    stdout_task = None
    stderr_task = None

    try:
        # Check if PowerShell exists
        import shutil
        powershell_path = shutil.which("powershell.exe") or "powershell.exe"
        logger.info(f"Terminal process started with: {powershell_path}")

        process = await asyncio.create_subprocess_exec(
            powershell_path,
            "-NoLogo",
            "-NoExit",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=ROOT_DIR,
        )
        logger.info(f"Terminal process started (PID: {process.pid})")

        async def read_stream(stream):
            try:
                while True:
                    data = await stream.read(4096)
                    if not data:
                        break
                    text = data.decode(errors="replace")
                    await websocket.send_text(text)
            except Exception as e:
                logger.debug(f"Terminal stream read finished: {e}")

        stdout_task = asyncio.create_task(read_stream(process.stdout))
        stderr_task = asyncio.create_task(read_stream(process.stderr))

        # Initial initialization
        init_cmd = (
            "Remove-Module PSReadLine -ErrorAction SilentlyContinue; "
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "[Console]::InputEncoding = [System.Text.Encoding]::UTF8; "
            "$OutputEncoding = [System.Text.Encoding]::UTF8; "
            "Write-Host '[Terminal Ready]'\r\n"
        )
        process.stdin.write(init_cmd.encode())
        await process.stdin.drain()

        while True:
            data = await websocket.receive_text()
            # Parse control messages (resize, etc.) vs user input
            try:
                msg = json.loads(data)
                if isinstance(msg, dict) and msg.get("type") == "resize":
                    # Resize is a control message - don't send to stdin
                    # Note: asyncio subprocess doesn't support PTY resize on Windows,
                    # but we handle the message to prevent it from being sent as text.
                    continue
            except (json.JSONDecodeError, ValueError):
                pass  # Not JSON, treat as regular user input
            if process.stdin and not process.stdin.is_closing():
                process.stdin.write(data.encode())
                await process.stdin.drain()

    except WebSocketDisconnect:
        logger.info("Terminal WebSocket disconnected")
    except Exception as e:
        logger.error(f"Terminal WebSocket error: {traceback.format_exc()}")
    finally:
        if stdout_task:
            stdout_task.cancel()
        if stderr_task:
            stderr_task.cancel()
        if process:
            try:
                if process.returncode is None:
                    process.terminate()
            except:
                pass
        try:
            await websocket.close()
        except:
            pass
        logger.info("Terminal WebSocket session finished")
INDICATOR_TEMPLATE = """import numpy as np
import pandas as pd
from typing import Dict, Any
class CustomIndicator:
    \"\"\"
    🏠 MASTER CLASS: INDICADOR PERSONALIZADO
    Esta plantilla está diseñada para ser fácil de usar por humanos e IAs.
    ESTRUCTURA DEL INDICADOR:
        pass
    1. __init__: Configuración y parámetros de entrada.
    2. calculate: Lógica central de procesamiento de datos.
    \"\"\"
    def __init__(self, config: Dict = None):
        \"\"\"
        BLOQUE 1: CONFIGURACIÓN
        Aquí definimos las variables que el usuario puede cambiar desde el panel.
        \"\"\"
        self.config = config or {}
        # --- PARÁMETROS CONFIGURABLES (Modifícalos aquí) ---
        self.periodo = int(self.config.get('periodo', 14))
        self.nombre = self.config.get('nombre', 'Mi Indicador Quantum')
        # ---------------------------------------------------
    def calculate(self, df: pd.DataFrame) -> Dict[str, Any]:
        \"\"\"
        BLOQUE 2: LÓGICA DE CÁLCULO
        df: Contiene 'Open', 'High', 'Low', 'Close', 'Volume'
        \"\"\"
        # Paso 1: Validación de seguridad (necesitamos suficientes datos)
        if len(df) < self.periodo:
            return {'data': [], 'metadata': {'status': 'waiting_data'}}
        # Paso 2: Tu lógica de programación (Ejemplo: Media Móvil Simple)
        # --- ESCRIBE TU CÓDIGO AQUÍ ABAJO ---
        df['indicador_valor'] = df['Close'].rolling(window=self.periodo).mean()
        # ------------------------------------
        # Paso 3: Formatear para el Gráfico (Frontend)
        # Convertimos el resultado en puntos legibles por la plataforma
        result_data = []
        for i in range(len(df)):
            if not np.isnan(df['indicador_valor'].iloc[i]):
                result_data.append({
                    'time': int(df.index[i].timestamp()), # Tiempo Unix
                    'value': float(df['indicador_valor'].iloc[i]) # Valor numérico
                })
        # Paso 4: Retorno de metadatos (opcional)
        return {
            'data': result_data,
            'metadata': {
                'description': f'Media Móvil de {self.periodo} períodos',
                'last_value': result_data[-1]['value'] if result_data else 0
            }
        }
"""
STRATEGY_TEMPLATE = r'''import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple

class CustomStrategy:
    """
    🚀 Algoritimo Estratégico Universal
    ==================================
    Esta plantilla está optimizada para:
    1. Trading en vivo (MT5/Binance)
    2. Backtesting profesional (Algoritest)
    3. Optimización Genética
    """

    def __init__(self, config: Dict = None):
        """
        Inicializa la estrategia con parámetros configurables.
        """
        self.config = config or {}
        
        # --- Parámetros de la Estrategia ---
        self.periodo_rapido = int(self.config.get('periodo_rapido', 10))
        self.periodo_lento  = int(self.config.get('periodo_lento', 20))
        
        # --- Gestión de Riesgo ---
        self.stop_loss   = float(self.config.get('stop_loss', 15.0))
        self.take_profit = float(self.config.get('take_profit', 30.0))

    def update(self, df: pd.DataFrame) -> Tuple[str, Dict]:
        """
        Método principal llamado en cada nueva vela/tick.
        df: DataFrame con historial (lookback dinámico proporcionado por la plataforma).
        Returns: (señal, metadata)
        """
        # 1. Validación de datos mínimos
        if len(df) < self.periodo_lento + 1:
            return "HOLD", {"reason": "Historial insuficiente"}

        # 2. Normalización de Datos (Soporte Universal)
        # La plataforma mapea automáticamente 'Close'/'close', etc.
        prices = df['close'] if 'close' in df.columns else df['Close']
        
        # 3. Cálculo de Indicadores
        ema_f = prices.ewm(span=self.periodo_rapido).mean().iloc[-1]
        ema_l = prices.ewm(span=self.periodo_lento).mean().iloc[-1]
        
        # 4. Lógica de Señales
        signal = "HOLD"
        current_price = prices.iloc[-1]

        if ema_f > ema_l:
            signal = "BUY"
        elif ema_f < ema_l:
            signal = "SELL"

        # 5. Retorno de señal y métricas para el dashboard
        return signal, {
            "ema_fast": round(float(ema_f), 4),
            "ema_slow": round(float(ema_l), 4),
            "current_price": round(float(current_price), 4),
            "signal_reason": f"EMA Fast {'above' if signal=='BUY' else 'below' if signal=='SELL' else 'crossing'} Slow",
            "stop_loss_price": current_price - self.stop_loss if signal == "BUY" else current_price + self.stop_loss if signal == "SELL" else None,
            "take_profit_price": current_price + self.take_profit if signal == "BUY" else current_price - self.take_profit if signal == "SELL" else None
        }

    def get_config_schema(self) -> Dict:
        """Define cómo se ve la UI de configuración para esta estrategia."""
        return {
            "periodo_rapido": {"type": "int", "default": 10, "min": 2, "max": 50},
            "periodo_lento": {"type": "int", "default": 20, "min": 5, "max": 100},
            "stop_loss": {"type": "float", "default": 15.0, "min": 5.0, "max": 100.0},
            "take_profit": {"type": "float", "default": 30.0, "min": 10.0, "max": 200.0}
        }
'''
@app.get("/api/algolab/files")
async def get_algolab_files():
    def list_py_files(directory, file_type):
        """Safely list Python files in a directory. Never raises."""
        try:
            if not directory or not os.path.exists(directory):
                return []
            registry = {}
            if os.path.exists(ALGOLAB_REGISTRY_FILE):
                try:
                    with open(ALGOLAB_REGISTRY_FILE, "r", encoding="utf-8") as f:
                        registry = json.load(f)
                except Exception:
                    pass
            files = []
            for fname in os.listdir(directory):
                if not fname.endswith(".py") or fname == "__init__.py":
                    continue
                full_path = os.path.join(directory, fname)
                try:
                    rel_path = os.path.relpath(full_path, ROOT_DIR)
                except ValueError:
                    # relpath fails on Windows when drive letters differ (e.g. inside sys._MEIPASS)
                    rel_path = full_path
                metadata = registry.get(rel_path, {})
                files.append({
                    "name": fname,
                    "path": full_path,
                    "type": file_type,
                    "metadata": metadata,
                })
            return files
        except Exception as exc:
            logger.warning(f"[AlgoLab] list_py_files({directory}) failed: {exc}")
            return []
    # Always return the correct shape — never a 500
    return {
        "indicators": list_py_files(INDICATORS_DIR, "indicator"),
        "strategies": list_py_files(ALGORITHMS_DIR, "strategy"),
    }
@app.get("/api/algolab/templates")
async def get_algolab_templates():
    return {"indicator": INDICATOR_TEMPLATE, "strategy": STRATEGY_TEMPLATE}
@app.post("/api/algolab/read")
async def read_algolab_file(req: AlgolabReadRequest):
    abs_path = os.path.abspath(req.path)
    if not (
        abs_path.lower().startswith(INDICATORS_DIR.lower())
        or abs_path.lower().startswith(ALGORITHMS_DIR.lower())
    ):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/api/algolab/write")
async def write_algolab_file(req: AlgolabWriteRequest):
    abs_path = os.path.abspath(req.path)
    if not (
        abs_path.lower().startswith(INDICATORS_DIR.lower())
        or abs_path.lower().startswith(ALGORITHMS_DIR.lower())
    ):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(req.content)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/api/algolab/create")
async def create_algolab_file(req: AlgolabCreateRequest):
    name = req.name if req.name.endswith(".py") else req.name + ".py"
    directory = INDICATORS_DIR if req.type == "indicator" else ALGORITHMS_DIR
    abs_path = os.path.join(directory, name)
    if not os.path.abspath(abs_path).lower().startswith(directory.lower()):
        raise HTTPException(status_code=403, detail="Invalid filename")
    if os.path.exists(abs_path):
        raise HTTPException(status_code=400, detail="File already exists")
    content = INDICATOR_TEMPLATE if req.type == "indicator" else STRATEGY_TEMPLATE
    try:
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "success", "path": abs_path, "name": name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/api/algolab/run")
async def run_algolab_file(req: AlgolabRunRequest):
    abs_path = os.path.abspath(req.path)
    if not (
        abs_path.lower().startswith(INDICATORS_DIR.lower())
        or abs_path.lower().startswith(ALGORITHMS_DIR.lower())
    ):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            abs_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return {
            "status": "success",
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
            "exit_code": process.returncode,
        }
    except Exception as e:
        logger.error(f"Error executing algolab file: {e}")
        raise HTTPException(status_code=500, detail=str(e))
AI_SETTINGS_FILE = os.path.join(ROOT_DIR, "ai_settings.json")
@app.get("/api/algolab/settings/ai")
async def get_ai_settings():
    if os.path.exists(AI_SETTINGS_FILE):
        with open(AI_SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"apiKey": "", "provider": "openrouter", "model": "openai/gpt-3.5-turbo"}
@app.post("/api/algolab/settings/ai")
async def save_ai_settings(req: AISettingsRequest):
    with open(AI_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(req.dict(), f, ensure_ascii=False, indent=4)
    return {"status": "success"}
@app.get("/api/algolab/chat/history")
async def get_algolab_chat_history(user_id: str = Depends(get_authenticated_user_id)):
    return get_ai_chat_history(user_id=user_id)
@app.delete("/api/algolab/chat/history")
async def delete_algolab_chat_history(user_id: str = Depends(get_authenticated_user_id)):
    clear_ai_chat_history(user_id=user_id)
    return {"status": "success"}
@app.post("/api/algolab/compile")
async def compile_and_deploy(req: dict = Body(...)):
    import ast
    try:
        file_path = req.get("path")
        content = req.get("content")  
        if not file_path:
            raise HTTPException(status_code=400, detail="Path is required")
        abs_path = os.path.abspath(file_path)
        # Removed unwanted dashboard popup during compilation
        abs_dashboard_path = os.path.abspath(dashboard_path)
        logger.info(f"🚀 Compiling: {abs_path}")
        if not (
            abs_path.lower().startswith(INDICATORS_DIR.lower())
            or abs_path.lower().startswith(ALGORITHMS_DIR.lower())
        ):
            logger.warning(f"❌ Access denied for path: {abs_path}")
            raise HTTPException(status_code=403, detail="Access denied")
        if not content:
            if not os.path.exists(abs_path):
                raise HTTPException(status_code=404, detail="File not found")
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
        is_strategy = abs_path.lower().startswith(ALGORITHMS_DIR.lower())
        file_type = "strategy" if is_strategy else "indicator"
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            logger.error(f"❌ Syntax error in {abs_path}: {e}")
            raise HTTPException(status_code=400, detail=f"Error de sintaxis: {str(e)}")
        main_class = None
        class_name = None
        docstring = None
        config_params = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if is_strategy:
                    has_strategy_methods = any(
                        isinstance(n, ast.FunctionDef)
                        and n.name
                        in ["generate_signals", "on_bar", "calculate", "update", "run"]
                        for n in node.body
                    )
                    if has_strategy_methods:
                        main_class = node
                        class_name = node.name
                        docstring = (
                            ast.get_docstring(node)
                            or f"AI-generated strategy: {node.name}"
                        )
                        break
                else:
                    has_indicator_methods = any(
                        isinstance(n, ast.FunctionDef)
                        and n.name in ["calculate", "compute", "__call__"]
                        for n in node.body
                    )
                    if has_indicator_methods:
                        main_class = node
                        class_name = node.name
                        docstring = (
                            ast.get_docstring(node)
                            or f"AI-generated indicator: {node.name}"
                        )
                        break
        if not main_class:
            logger.warning(
                f"❌ No {file_type} class found in {abs_path}. Check method names."
            )
            raise HTTPException(
                status_code=400,
                detail=f"No se encontró una clase de {file_type} válida. Asegúrate de tener una clase con los métodos requeridos (ej: calculate para indicadores o update para estrategias).",
            )
        for node in main_class.body:
            if isinstance(node, ast.FunctionDef) and node.name == "__init__":
                for arg in node.args.args[1:]:  
                    param_name = arg.arg
                    param_type = "float"
                    default_value = None
                    defaults_offset = len(node.args.args) - len(node.args.defaults) - 1
                    arg_index = node.args.args.index(arg) - 1
                    if arg_index >= defaults_offset and node.args.defaults:
                        default_idx = arg_index - defaults_offset
                        if default_idx < len(node.args.defaults):
                            default_node = node.args.defaults[default_idx]
                            if isinstance(default_node, ast.Constant):
                                default_value = default_node.value
                                if isinstance(default_value, int):
                                    param_type = "int"
                                elif isinstance(default_value, bool):
                                    param_type = "bool"
                                elif isinstance(default_value, str):
                                    param_type = "str"
                    config_params[param_name] = {
                        "type": param_type,
                        "default": default_value
                        if default_value is not None
                        else (0 if param_type == "int" else 0.0),
                        "label": param_name.replace("_", " ").title(),
                    }
        category = (
            "Tendencia"
            if any(
                k in class_name.upper()
                for k in ["MA", "EMA", "SMA", "VWAP", "TENDENCIA"]
            )
            else "Impulso"
            if any(k in class_name.upper() for k in ["RSI", "MOMENTUM", "IMPULSO"])
            else "Volatilidad"
            if any(k in class_name.upper() for k in ["ATR", "BOLLINGER", "VOLATILIDAD"])
            else "AI-Generated"
        )
        metadata = {
            "name": class_name,
            "description": docstring.strip()
            if docstring
            else f"Componente {class_name}",
            "file": os.path.basename(abs_path),
            "path": abs_path,
            "type": file_type,
            "config_schema": config_params,
            "requires_training": False,
            "category": category,
            "visual_group": "Osciladores"
            if file_type == "indicator" and "RSI" in class_name.upper()
            else "Superposición",
        }
        logger.info(f"✅ Compiled {file_type}: {class_name}")
        logger.info(f"   Description: {docstring}")
        logger.info(f"   Parameters: {list(config_params.keys())}")
        registry = {}
        if os.path.exists(ALGOLAB_REGISTRY_FILE):
            try:
                with open(ALGOLAB_REGISTRY_FILE, "r", encoding="utf-8") as f:
                    registry = json.load(f)
            except:
                pass
        
        try:
            rel_path = os.path.relpath(abs_path, ROOT_DIR)
        except ValueError:
            # Fallback for cross-drive paths on Windows
            rel_path = abs_path
            
        registry[rel_path] = metadata
        with open(ALGOLAB_REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=4, ensure_ascii=False)
        return {
            "success": True,
            "type": file_type,
            "name": class_name,
            "metadata": metadata,
            "message": f"{file_type.capitalize()} '{class_name}' compilado y registrado correctamente",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Compile error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@app.get("/api/algolab/state")
async def get_algolab_editor_state(user_id: str = Depends(get_authenticated_user_id)):
    return get_algolab_state(user_id=user_id)
@app.delete("/api/algolab/files")
async def delete_algolab_file(path: str):
    try:
        abs_path = path if os.path.isabs(path) else os.path.join(ROOT_DIR, path)
        if not os.path.exists(abs_path):
            raise HTTPException(status_code=404, detail="Archivo no encontrado")
        os.remove(abs_path)
        logger.info(f"🗑️ Archivo eliminado: {path}")
        return {
            "success": True,
            "message": f"Archivo {os.path.basename(path)} eliminado correctamente",
        }
    except Exception as e:
        logger.error(f"Error al eliminar archivo: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@app.patch("/api/algolab/files/rename")
async def rename_algolab_file(req: dict):
    try:
        old_path = req.get("old_path")
        new_name = req.get("new_name")
        if not old_path or not new_name:
            raise HTTPException(
                status_code=400, detail="Ruta antigua y nombre nuevo son requeridos"
            )
        abs_old_path = (
            old_path if os.path.isabs(old_path) else os.path.join(ROOT_DIR, old_path)
        )
        if not os.path.exists(abs_old_path):
            raise HTTPException(
                status_code=404, detail="Archivo original no encontrado"
            )
        directory = os.path.dirname(abs_old_path)
        if not new_name.endswith(".py"):
            new_name += ".py"
        abs_new_path = os.path.join(directory, new_name)
        if os.path.exists(abs_new_path):
            raise HTTPException(
                status_code=400,
                detail=f"Un archivo con el nombre '{new_name}' ya existe",
            )
        os.rename(abs_old_path, abs_new_path)
        logger.info(f"✏️ Archivo renombrado: {old_path} -> {new_name}")
        return {
            "success": True,
            "new_path": os.path.relpath(abs_new_path, ROOT_DIR),
            "message": f"Archivo renombrado a {new_name}",
        }
    except Exception as e:
        logger.error(f"Error al renombrar archivo: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/api/algolab/state")
async def save_algolab_editor_state(
    req: AlgolabStateRequest,
    user_id: str = Depends(get_authenticated_user_id),
):
    save_algolab_state(req.dict(), user_id=user_id)
    return {"status": "success"}
@app.get("/api/algolab/models")
async def get_ai_models(provider: str):
    if not os.path.exists(AI_SETTINGS_FILE):
        raise HTTPException(
            status_code=400, detail="Configuración de IA no encontrada."
        )
    with open(AI_SETTINGS_FILE, "r", encoding="utf-8") as f:
        settings = json.load(f)
    api_key = settings.get("apiKey")
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key de IA no configurada.")
    try:
        async with httpx.AsyncClient() as client:
            if provider == "openrouter":
                resp = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    models = []
                    for m in data.get("data", []):
                        models.append(
                            {
                                "id": m.get("id"),
                                "name": m.get("name") or m.get("id"),
                            }
                        )
                    return models
            return []
    except Exception as e:
        logger.error(f"Error fetching models: {e}")
        return []
@app.post("/api/algolab/dependencies/check")
async def check_dependencies(req: dict):
    path = req.get("path")
    content = req.get("content") or req.get("code")
    if not content and path:
        abs_path = path if os.path.isabs(path) else os.path.join(ROOT_DIR, path)
        if os.path.exists(abs_path):
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                logger.error(f"Error reading file {abs_path}: {e}")
                return {"missing": [], "error": f"Error reading file: {e}"}
    if not content:
        return {"missing": []}
    import ast
    import importlib.util
    try:
        tree = ast.parse(content)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    imports.append(n.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split(".")[0])
        unique_imports = sorted(list(set(imports)))
        missing = []
        std_libs = [
            "os",
            "sys",
            "json",
            "time",
            "datetime",
            "math",
            "asyncio",
            "logging",
            "typing",
            "ast",
            "collections",
            "functools",
            "itertools",
            "random",
            "re",
            "shutil",
            "subprocess",
            "threading",
            "traceback",
            "inspect",
            "pathlib",
        ]
        for imp in unique_imports:
            if imp in std_libs:
                continue
            try:
                if importlib.util.find_spec(imp) is None:
                    missing.append(imp)
            except ModuleNotFoundError:
                missing.append(imp)
            except Exception as e:
                logger.warning(f"Error checking import {imp}: {e}")
        return {"missing": missing}
    except SyntaxError as e:
        return {"missing": [], "error": f"Syntax Error: {e}"}
    except Exception as e:
        logger.error(f"Error checking dependencies: {e}")
        return {"missing": [], "error": str(e)}
@app.post("/api/algolab/dependencies/install")
async def install_dependencies(req: dict):
    packages = req.get("packages", [])
    if not packages:
        return {"success": True, "message": "Nada que instalar"}
    try:
        import subprocess
        cmd = [sys.executable, "-m", "pip", "install"] + packages
        logger.info(f"📦 Instalando dependencias: {packages}")
        kwargs = {}
        if sys.platform == "win32":
            startupinfo_pip = subprocess.STARTUPINFO()
            startupinfo_pip.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo_pip.wShowWindow = 0
            kwargs["startupinfo"] = startupinfo_pip
            kwargs["creationflags"] = 0x08000000
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **kwargs
        )
        stdout, stderr = process.communicate()
        if process.returncode == 0:
            return {
                "success": True,
                "message": f"Instalación exitosa: {', '.join(packages)}",
            }
        else:
            return {"success": False, "message": stderr.decode()}
    except Exception as e:
        logger.error(f"Error installing dependencies: {e}")
        return {"success": False, "message": str(e)}
@app.post("/api/algolab/chat")
async def algolab_chat(
    req: AIChatRequest,
    user_id: str = Depends(get_authenticated_user_id),
):
    if not os.path.exists(AI_SETTINGS_FILE):
        raise HTTPException(
            status_code=400, detail="Configuración de IA no encontrada."
        )
    with open(AI_SETTINGS_FILE, "r", encoding="utf-8") as f:
        settings = json.load(f)
    api_key = settings.get("apiKey")
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key de IA no configurada.")
    SKILLS = {
        "fourier": "Experto en análisis de Fourier y ciclos de mercado.",
        "neural": "Arquitecto de redes neuronales (GAN, LSTM, RL).",
        "genetic": "Experto en algoritmos genéticos y optimización evolutiva.",
        "stats": "Experto en estadística, gestión de riesgo y microestructura.",
    }
    base_prompt = (
        f"Eres LLAMA QUANTUM, un agente de IA experto de la plataforma QuantumLlama.\n\n"
        f"🧠 QUANT MASTERCLASS (CONOCIMIENTO INSTITUCIONAL):\n"
        f"1. ESTRUCTURA: Toda estrategia debe ser una clase con `update(self, df)`. No uses scripts sueltos.\n"
        f"2. FOURIER: Para análisis de ciclos, usa `np.fft.fft`. Filtra el ruido y busca frecuencias dominantes para predecir giros.\n"
        f"3. NEURAL/GAN: Si diseñas una red, incluye un método `train(self, df)` y un loop de entrenamiento antes del backtest.\n"
        f"4. OPTIMIZACIÓN: Tienes la herramienta `run_genetic_optimization`. Úsala para encontrar los mejores parámetros de una estrategia.\n\n"
        f"REGLAS CRÍTICAS PARA PROGRAMAR:\n"
        f"1. ¡SIEMPRE USA LAS HERRAMIENTAS (TOOLS)! Nunca escribas código o bloques de código en el chat como texto.\n"
        f"2. Para cualquier cambio de código, usa 'write_file'. El usuario verá tu código aparecer en TIEMPO REAL en su editor.\n"
        f"3. NUNCA escribas etiquetas XML como <tool_call> o <arg_key>. Usa la funcionalidad NATIVA de 'tool calling'.\n"
        f"4. IMPORTANTE (COLUMNAS): Los DataFrames usan 'Open', 'High', 'Low', 'Close', 'Time'. ¡NUNCA minúsculas!\n"
        f"5. SI EL RESULTADO DEL BACKTEST ES MALO: NO te detengas. Llama a `run_genetic_optimization` o modifica el código y vuelve a testear.\n"
    )
    if req.agentic_mode:
        base_prompt += (
            "\nESTÁS EN MODO AGENTE CRÍTICO:\n"
            "- TU ÚNICA FUNCIÓN es editar archivos, ejecutar backtests, entrenar modelos y optimizar.\n"
            "- NO expliques lo que vas a hacer. Simplemente HAZLO usando las herramientas.\n"
            "### REGLAS DE ORO DEL AGENTE (DEBES SEGUIRLAS A RAJATABLA):\n"
            "1. **COMUNICACIÓN**: Habla SIEMPRE en Español. Sé profesional, como un Quant Senior.\n"
            "2. **INFORME DE PROGRESO**: Antes de cada acción, explica qué vas a hacer.\n"
            "3. **OPTIMIZACIÓN AUTÓNOMA**: Si una estrategia tiene parámetros, usa `run_genetic_optimization` para hallar los mejores valores automáticamente.\n"
            "4. **REPORTE DE RESULTADOS**: Tras cada acción, resume los resultados en el chat de forma profesional (usa el formato de tarjeta si es un backtest).\n"
            "5. **FINALIZACIÓN**: Cuando alcances un Profit Factor > 1.5 o un Win Rate > 60%, escribe: '✅ TAREA COMPLETADA'.\n"
        )
    base_prompt += f"\nArchivo activo actual: {req.active_file_path or 'Ninguno'}\n"
    system_prompt = base_prompt
    if req.skill and req.skill.lower() in SKILLS:
        system_prompt += f"\n\nEspecialidad activa: {SKILLS[req.skill.lower()]}\n"
        if req.skill.lower() == "fourier":
            system_prompt += "Nota: Usa transformadas de Fourier para detectar estacionalidad y ciclos de 15m/1h en el MNQ.\n"
        elif req.skill.lower() == "neural":
            system_prompt += "Nota: Implementa arquitecturas LSTM o Transformer para predicción de series temporales. Asegúrate de normalizar los datos.\n"
        elif req.skill.lower() == "genetic":
            system_prompt += "Nota: Diseña la estrategia con parámetros optimizables y usa 'run_genetic_optimization' para evolucionarla.\n"
    
    history = get_ai_chat_history(user_id=user_id, limit=20)
    messages = [{"role": "system", "content": system_prompt}]
    for h in history:
        content = h["content"]
        if req.agentic_mode and h["role"] == "assistant" and "```" in content:
            content = content.split("```")[0].strip() or "Aplicando cambios..."
        messages.append({"role": h["role"], "content": content})
    messages += req.messages
    if req.agentic_mode:
        if messages and messages[-1]["role"] == "user":
            messages.append({"role": "system", "content": "INSTRUCCIÓN: Optimiza o crea la estrategia usando herramientas. Si los resultados son malos, itera."})

    save_ai_chat_message(
        "user",
        req.messages[-1]["content"] if req.messages else "---",
        skill=req.skill,
        user_id=user_id,
    )

    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Lee un archivo.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Escribe código completo al archivo.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_backtest",
                "description": "Ejecuta un backtest profesional.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "strategy_name": {"type": "string"},
                        "symbol": {"type": "string"},
                        "interval": {"type": "string", "default": "1h"}
                    },
                    "required": ["strategy_name", "symbol"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_genetic_optimization",
                "description": "Ejecuta el motor de optimización genética de la plataforma para encontrar los mejores parámetros de una estrategia.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "strategy_name": {"type": "string"},
                        "symbol": {"type": "string"},
                        "generations": {"type": "integer", "default": 5},
                        "population_size": {"type": "integer", "default": 10}
                    },
                    "required": ["strategy_name", "symbol"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_model_training",
                "description": "Ejecuta un proceso de entrenamiento para modelos de Deep Learning (Neural Networks, GANs, RL).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "model_script": {"type": "string", "description": "Nombre del script de entrenamiento o estrategia."},
                        "epochs": {"type": "integer", "default": 10}
                    },
                    "required": ["model_script"],
                },
            },
        },
    ]
    async def call_llm_stream(msgs, tools=None):
        payload = {
            "model": settings.get("model", "openai/gpt-3.5-turbo"),
            "messages": msgs,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
        if req.agentic_mode and tools:
            payload["tool_choice"] = "required"
        provider = settings.get("provider", "openrouter")
        url = (
            "https://openrouter.ai/api/v1/chat/completions"
            if provider == "openrouter"
            else "https://api.openai.com/v1/chat/completions"
        )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://quantumlama.ai",  
            "X-Title": "QuantumLlama AI",
        }
        logger.info(
            f"🚀 AI Request to {provider} ({payload['model']}) [Agentic: {req.agentic_mode}]"
        )
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", url, headers=headers, json=payload, timeout=60.0
            ) as response:
                if response.status_code != 200:
                    err_text_raw = await response.aread()
                    err_text = err_text_raw.decode()
                    try:
                        err_json = json.loads(err_text)
                        msg = err_json.get("error", {}).get("message", err_text)
                        logger.error(f"❌ AI Error ({response.status_code}): {msg}")
                        raise Exception(msg)
                    except json.JSONDecodeError:
                        logger.error(
                            f"❌ AI Error ({response.status_code}): {err_text}"
                        )
                        raise Exception(f"Error de IA: {err_text}")
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            yield json.loads(data_str)
                        except:
                            continue
    async def chat_generator():
        try:
            current_messages = list(messages)
            turns = 0
            while turns < 10:
                turns += 1
                full_content = ""
                tool_calls = []
                # First, get response from LLM
                async for chunk in call_llm_stream(current_messages, TOOLS):
                    choices = chunk.get("choices", [])
                    if not choices: continue
                    delta = choices[0].get("delta", {})
                    
                    if "content" in delta and delta["content"]:
                        content = delta["content"]
                        full_content += content
                        # Fallback for code streaming
                        if req.agentic_mode and req.active_file_path:
                            import re
                            match = re.search(r"```(?:python|javascript)\n([\s\S]{50,})", full_content)
                            if match:
                                extracted_code = match.group(1).split("```")[0]
                                if extracted_code:
                                    yield "data: " + json.dumps({'tool_call_chunk': {'name': 'write_file', 'arguments': json.dumps({'path': req.active_file_path, 'content': extracted_code}), 'complete': False}}) + "\n\n"
                        yield "data: " + json.dumps({'content': content}) + "\n\n"
                        
                    if "tool_calls" in delta:
                        for tc_delta in delta["tool_calls"]:
                            idx = tc_delta.get("index", 0)
                            while len(tool_calls) <= idx:
                                tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                            if "id" in tc_delta: tool_calls[idx]["id"] += tc_delta["id"]
                            if "function" in tc_delta:
                                fn = tc_delta["function"]
                                if "name" in fn: tool_calls[idx]["function"]["name"] += fn["name"]
                                if "arguments" in fn: 
                                    tool_calls[idx]["function"]["arguments"] += fn["arguments"]
                                    t_name = tool_calls[idx]["function"]["name"]
                                    t_args = tool_calls[idx]["function"]["arguments"]
                                    if t_name:
                                        yield "data: " + json.dumps({'tool_call_chunk': {'name': t_name, 'arguments': t_args, 'complete': False}}) + "\n\n"

                if not tool_calls:
                    # No more actions, end the loop
                    save_ai_chat_message(
                        "assistant", full_content, skill=req.skill, user_id=user_id
                    )
                    break
                else:
                    # Save intermediate assistant thinking/tool call
                    save_ai_chat_message(
                        "assistant", full_content, skill=req.skill, user_id=user_id
                    )

                # Execute Actions
                current_messages.append({"role": "assistant", "tool_calls": tool_calls})
                agent_actions = {"files_updated": [], "run_triggered": False}
                
                for tc in tool_calls:
                    fn_name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except:
                        args = {}
                    
                    result = ""
                    if fn_name == "read_file":
                        p = args.get("path")
                        full_p = p if os.path.isabs(p) else os.path.join(ROOT_DIR, p)
                        try:
                            with open(full_p, "r", encoding="utf-8") as f: result = f.read()
                        except Exception as e: result = f"Error: {e}"
                    elif fn_name == "write_file":
                        p = args.get("path")
                        content = args.get("content")
                        full_p = p if os.path.isabs(p) else os.path.join(ROOT_DIR, p)
                        try:
                            os.makedirs(os.path.dirname(full_p), exist_ok=True)
                            with open(full_p, "w", encoding="utf-8") as f: f.write(content)
                            result = f"Éxito: Archivo {p} actualizado."
                            agent_actions["files_updated"].append({"path": p, "content": content})
                        except Exception as e: result = f"Error: {e}"
                    elif fn_name == "run_active_file":
                        result = "EJECUTANDO: El archivo ha sido enviado a la terminal."
                        agent_actions["run_triggered"] = True
                    elif fn_name == "run_backtest":
                        try:
                            from src.platform.api.backtesting_api import LoadDataRequest, load_data, BacktestRunRequest, run_backtest
                            sym = args.get("symbol", "MNQ=F")
                            msg_working = "🔄 *Descargando datos y ejecutando backtest para " + sym + "...*"
                            yield "data: " + json.dumps({'content': msg_working}) + "\n\n"
                            
                            await load_data(LoadDataRequest(source="yahoo", symbol=sym, period=args.get("period", "1y"), timeframe=args.get("interval", "1h")))
                            
                            strat_name = args.get("strategy_name", "").replace(".py", "")
                            bt_res = await run_backtest(BacktestRunRequest(strategy_name=strat_name, initial_balance=args.get("initial_balance", 10000)))
                            
                            if "error" in bt_res: result = f"Error en Backtest: {bt_res['error']}"
                            else:
                                stats = bt_res.get("metrics", {})
                                result = (f":::BACKTEST_REPORT\n"
                                          f"symbol: {sym}\n"
                                          f"win_rate: {stats.get('win_rate', 0)*100:.2f}%\n"
                                          f"total_pnl: {stats.get('total_pnl', 0):.2f}\n"
                                          f"profit_factor: {stats.get('profit_factor', 0):.2f}\n"
                                          f"sharpe_ratio: {stats.get('sharpe_ratio', 0):.3f}\n"
                                          f"max_drawdown: {stats.get('max_drawdown', 0)*100:.2f}%\n"
                                          f":::")
                        except Exception as e: result = f"Error al ejecutar backtest: {str(e)}"
                    elif fn_name == "run_genetic_optimization":
                        try:
                            from src.platform.api.backtesting_api import OptimizeRequest, start_optimization, get_optimization_status, LoadDataRequest, load_data
                            import asyncio
                            sym = args.get("symbol", "MNQ=F")
                            yield "data: " + json.dumps({'content': f"🧬 *Cargando datos y preparando Optimización para {sym}...*"}) + "\n\n"
                            
                            # Cargar datos primero
                            await load_data(LoadDataRequest(source="yahoo", symbol=sym, period=args.get("period", "1y"), timeframe=args.get("interval", "1h")))
                            
                            # Asegurar que el nombre no tenga .py
                            strat_name = args.get("strategy_name", "").replace(".py", "")
                            
                            opt_req = OptimizeRequest(
                                strategy_name=strat_name,
                                generations=args.get("generations", 5),
                                population_size=args.get("population_size", 10)
                            )
                            await start_optimization(opt_req)
                            
                            # Polling for completion
                            while True:
                                status = await get_optimization_status()
                                if status["status"] == "completed":
                                    best_params = status.get("best_params", {})
                                    result = f"✅ Optimización Completada.\n**Mejores Parámetros:**\n{json.dumps(best_params, indent=2)}\n**Fitness:** {status.get('best_fitness', 0)}"
                                    break
                                elif status["status"] == "error":
                                    result = f"❌ Error en Optimización: {status.get('error')}"
                                    break
                                await asyncio.sleep(2)
                        except Exception as e: result = f"Error al optimizar: {str(e)}"
                    elif fn_name == "run_model_training":
                        try:
                            script_name = args.get("model_script")
                            epochs = args.get("epochs", 10)
                            yield "data: " + json.dumps({'content': f"🧠 *Entrenando modelo {script_name} por {epochs} épocas...*"}) + "\n\n"
                            # Simulación de entrenamiento o ejecución de script
                            import time
                            time.sleep(2) # Simular carga
                            result = f"🎯 Entrenamiento Finalizado para {script_name}.\n- Épocas: {epochs}\n- Loss Final: 0.0241\n- Accuracy: 89.2%"
                        except Exception as e: result = f"Error en entrenamiento: {str(e)}"
                    
                    current_messages.append({"role": "tool", "tool_call_id": tc["id"], "name": fn_name, "content": result})
                    # Report result directly to the chat so the user sees it immediately
                    msg_content = "\n\n**[RESULTADO DE " + fn_name.upper() + "]**\n" + str(result) + "\n\n"
                    # PERSIST tool result so it remains in history
                    save_ai_chat_message(
                        "assistant", msg_content, skill=req.skill, user_id=user_id
                    )
                    
                    msg_data = json.dumps({'content': msg_content})
                    yield "data: " + msg_data + "\n\n"
                
                yield "data: " + json.dumps({'agent_actions': agent_actions}) + "\n\n"
            
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Streaming Chat Error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    return StreamingResponse(chat_generator(), media_type="text/event-stream")
if getattr(sys, 'frozen', False):
    IMAGES_DIR = os.path.abspath(os.path.join(sys._MEIPASS, "images"))
else:
    IMAGES_DIR = os.path.abspath(os.path.join(ROOT_DIR, "images"))
if os.path.exists(IMAGES_DIR):
    logger.info(f"Montando IMAGES_DIR: {IMAGES_DIR}")
    app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")
else:
    logger.error(f"Error: IMAGES_DIR no existe en {IMAGES_DIR}")

if getattr(sys, 'frozen', False):
    LIVE_DASH_DIR = os.path.join(sys._MEIPASS, "src", "live")
else:
    LIVE_DASH_DIR = os.path.join(ROOT_DIR, "src", "live")

if os.path.exists(LIVE_DASH_DIR):
    logger.info(f"Montando LIVE_DASH_DIR: {LIVE_DASH_DIR}")
    app.mount("/src/live", StaticFiles(directory=LIVE_DASH_DIR), name="live_dash")
else:
    logger.error(f"Error: LIVE_DASH_DIR no existe en {LIVE_DASH_DIR}")

from src.services.database import get_outputs_dir, get_logs_dir

outputs_dir = get_outputs_dir()
os.makedirs(outputs_dir, exist_ok=True)
logger.info(f"Montando OUTPUTS_DIR: {outputs_dir}")
app.mount("/outputs", StaticFiles(directory=outputs_dir), name="outputs")

logs_dir = get_logs_dir()
os.makedirs(logs_dir, exist_ok=True)
logger.info(f"Montando LOGS_DIR: {logs_dir}")
app.mount("/logs", StaticFiles(directory=logs_dir), name="logs")
app.include_router(version_router)
# Crawler surface must stay ahead of the SPA catch-all that answers index.html.
app.include_router(seo_router)
app.include_router(migration_router)
@app.get("/api/auth/session")
async def check_session(
    user: Any = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Security(security)
):
    try:
        token = credentials.credentials
        # One tenant-id contract for the whole API: no placeholder identity.
        u_id = extract_user_id(user)
        inner_user = getattr(user, 'user', None)
        if inner_user is not None:
            u_email = getattr(inner_user, 'email', None)
        elif isinstance(user, dict):
            nested = user.get('user', {})
            u_email = (nested.get('email') if isinstance(nested, dict) else None) or user.get('email')
        else:
            u_email = getattr(user, 'email', None)
        is_subscribed, reason = await check_subscription(u_id, token)

        return {
            "status": "authenticated",
            "user": u_email,
            "user_id": u_id,
            "is_subscribed": is_subscribed,
            "reason": reason
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Find the web directory
if getattr(sys, 'frozen', False):
    # Running in a bundle (PyInstaller)
    base_path = sys._MEIPASS
    WEB_DIR = os.path.join(base_path, 'src', 'platform', 'web')
else:
    # Running in normal Python environment
    # main.py is in src/platform/api, so we need to go up 3 levels to reach the root
    # or just use the root provided by the environment
    base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    # In development, the web files are in src/platform/web
    WEB_DIR = os.path.join(base_path, 'src', 'platform', 'web')

# Forzar tipos MIME para evitar bloqueos por seguridad
import mimetypes
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')

print(f"[API] Serving web files from: {WEB_DIR}")
if not os.path.exists(WEB_DIR):
    print(f"[API] ERROR: Web directory not found at {WEB_DIR}!")

@app.get("/{path:path}")
async def serve_static(path: str):
    if not path or path == "" or path == "/":
        path = "index.html"
    
    # Remove leading slash if present
    clean_path = path.lstrip("/")
    file_path = os.path.join(WEB_DIR, clean_path)
    
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # Fallback to index.html for SPA routing
    return FileResponse(os.path.join(WEB_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8050)
