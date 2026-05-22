import asyncio
import os
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query
from pydantic import BaseModel
from src.services.mt5_manager import get_manager
from src.services.crypto_manager import get_crypto_manager
from src.live.crypto_connector import get_connector
from src.services.tradovate_manager import get_tradovate_manager
from src.services.ninjatrader_manager import get_nt8_manager
router = APIRouter(prefix="/api/accounts", tags=["Accounts"])
logger = logging.getLogger(__name__)
class AccountCreate(BaseModel):
    name: str
    broker: str
    server: Optional[str] = None
    login: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    passphrase: Optional[str] = None
    app_id: Optional[str] = None
    app_version: Optional[str] = "1.0.0"
    cid: Optional[str] = None
    sec: Optional[str] = None
    exchange_dir: Optional[str] = None
    account_type: str = "demo"
    platform: str = "mt5"
    environment: Optional[str] = "demo"
    mirror_trading: Optional[bool] = True
class AccountResponse(BaseModel):
    id: str
    name: str
    broker: str
    server: Optional[str] = None
    login: Optional[str] = None
    api_key: Optional[str] = None
    exchange_dir: Optional[str] = None
    account_type: str
    status: str
    is_master: bool
    mirror_trading: Optional[bool] = False
    created_at: str
    platform: str = "mt5"
class AccountUpdate(BaseModel):
    name: Optional[str] = None
    account_type: Optional[str] = None
    password: Optional[str] = None
    api_secret: Optional[str] = None
    passphrase: Optional[str] = None
    exchange_dir: Optional[str] = None
    mirror_trading: Optional[bool] = None
class ConnectionTestResponse(BaseModel):
    success: bool
    balance: Optional[float] = None
    equity: Optional[float] = None
    server: Optional[str] = None
    error: Optional[str] = None
@router.get("", response_model=List[AccountResponse])
async def get_accounts():
    mt5_manager = get_manager()
    crypto_manager = get_crypto_manager()
    tradovate_manager = get_tradovate_manager()
    accounts = []
    for acc in mt5_manager.get_accounts():
        acc["platform"] = "mt5"
        accounts.append(acc)
    for acc in crypto_manager.get_accounts():
        acc["platform"] = "crypto"
        accounts.append(acc)
    for acc in tradovate_manager.get_accounts():
        acc["platform"] = "tradovate"
        accounts.append(acc)
    nt8_manager = get_nt8_manager()
    for acc in nt8_manager.get_accounts():
        acc["platform"] = "nt8"
        accounts.append(acc)
    return accounts
@router.post("", response_model=AccountResponse)
async def add_account(account: AccountCreate):
    try:
        # Wrap manager getting in try/except to catch instantiation errors
        try:
            if account.platform == "mt5":
                manager = get_manager()
            elif account.platform == "crypto":
                manager = get_crypto_manager()
            elif account.platform == "tradovate":
                manager = get_tradovate_manager()
            elif account.platform == "nt8":
                manager = get_nt8_manager()
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported platform: {account.platform}")
        except Exception as manager_exc:
            logger.error(f"Failed to initialize {account.platform} manager: {manager_exc}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Manager init failure: {str(manager_exc)}")

        if account.platform == "mt5":
            if not account.login or not account.server or not account.password:
                raise HTTPException(status_code=400, detail="Missing MT5 credentials")
            existing = manager.get_accounts()
            for acc in existing:
                if acc["login"] == account.login and acc["server"] == account.server:
                    raise HTTPException(status_code=400, detail="Account already exists")
            new_account = manager.add_account(
                name=account.name,
                broker=account.broker,
                server=account.server,
                login=account.login,
                password=account.password,
                account_type=account.account_type,
            )
            new_account["platform"] = "mt5"
            return new_account
        elif account.platform == "crypto":
            if not account.api_key or not account.api_secret:
                raise HTTPException(status_code=400, detail="Missing Crypto API keys")
            new_account = manager.add_account(
                name=account.name,
                broker=account.broker,
                api_key=account.api_key,
                api_secret=account.api_secret,
                passphrase=account.passphrase,
                account_type=account.account_type
            )
            new_account["platform"] = "crypto"
            return new_account
        elif account.platform == "tradovate":
            if not account.username or not account.password or not account.cid or not account.sec:
                raise HTTPException(status_code=400, detail="Missing Tradovate credentials (Username, Password, CID or Secret)")
            new_account = manager.add_account(
                name=account.name,
                username=account.username,
                password=account.password,
                app_id=account.app_id or "Quantum",
                app_version=account.app_version or "1.0.0",
                cid=account.cid,
                sec=account.sec,
                environment=account.environment or "demo"
            )
            new_account["platform"] = "tradovate"
            return new_account
        elif account.platform == "nt8":
            if not account.exchange_dir:
                raise HTTPException(status_code=400, detail="Missing NinjaTrader Exchange Directory")
            new_account = manager.add_account(
                name=account.name,
                exchange_dir=account.exchange_dir,
                account_type=account.account_type,
                mirror_trading=account.mirror_trading if account.mirror_trading is not None else True
            )
            new_account["platform"] = "nt8"
            return new_account
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported platform: {account.platform}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding account: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
@router.patch("/{account_id}")
async def update_account(account_id: str, update: AccountUpdate, platform: str = Query("mt5")):
    if platform == "mt5":
        manager = get_manager()
    elif platform == "crypto":
        manager = get_crypto_manager()
    elif platform == "tradovate":
        manager = get_tradovate_manager()
    elif platform == "nt8":
        manager = get_nt8_manager()
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported platform: {platform}")
    updated = manager.update_account(account_id, update.dict(exclude_unset=True))
    if updated:
        return updated
    raise HTTPException(status_code=404, detail="Account not found")
@router.delete("/{account_id}")
async def remove_account(account_id: str, platform: str = Query("mt5")):
    if platform == "mt5":
        manager = get_manager()
    elif platform == "crypto":
        manager = get_crypto_manager()
    elif platform == "tradovate":
        manager = get_tradovate_manager()
    elif platform == "nt8":
        manager = get_nt8_manager()
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported platform: {platform}")
    if manager.remove_account(account_id):
        return {"status": "deleted", "id": account_id}
    raise HTTPException(status_code=404, detail="Account not found")
@router.post("/{account_id}/test", response_model=ConnectionTestResponse)
async def test_existing_account_connection(account_id: str, platform: str = Query("mt5")):
    if platform == "mt5":
        manager = get_manager()
        return manager.test_connection(account_id)
    elif platform == "crypto":
        from src.live.crypto_connector import get_connector
        connector = get_connector(account_id)
        if not connector:
            return {"success": False, "error": "Could not create crypto connector. Check your credentials."}
        try:
            balance = connector.get_balance()
            equity = connector.get_equity()
            return {
                "success": True, 
                "balance": balance,
                "equity": equity,
                "server": connector.exchange_id.upper()
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    elif platform == "tradovate":
        from src.live.tradovate_connector import get_tradovate_connector
        connector = get_tradovate_connector(account_id)
        if not connector:
            return {"success": False, "error": "Could not create Tradovate connector. Check your credentials."}
        try:
            balance = connector.get_balance()
            return {
                "success": True,
                "balance": balance,
                "equity": balance,
                "server": f"TRADOVATE {connector.environment.upper()}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    elif platform == "nt8":
        manager = get_nt8_manager()
        account = manager.get_account(account_id)
        if not account:
             return {"success": False, "error": "Account not found"}
        ex_dir = account.get("exchange_dir")
        if not ex_dir or not os.path.exists(ex_dir):
             return {"success": False, "error": f"Exchange directory not found: {ex_dir}"}
        return {
            "success": True,
            "balance": 0,
            "equity": 0,
            "server": "NinjaTrader Local Bridge"
        }
    return {"success": False, "error": f"Platform {platform} not supported for testing"}
@router.post("/{account_id}/master")
async def set_master_account(account_id: str, platform: str = Query("mt5")):
    if platform == "mt5":
        manager = get_manager()
    elif platform == "crypto":
        manager = get_crypto_manager()
    elif platform == "tradovate":
        manager = get_tradovate_manager()
    elif platform == "nt8":
        manager = get_nt8_manager()
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported platform: {platform}")
    if manager.set_master_account(account_id):
        return {"status": "success", "master_account_id": account_id}
    raise HTTPException(status_code=400, detail="Failed to set master account")
@router.post("/{account_id}/connect")
async def connect_account(account_id: str, platform: str = Query("mt5"), data: Dict[str, Any] = Body(None)):
    actual_platform = platform
    if platform == "mt5" and data and "platform" in data:
        actual_platform = data["platform"]
    if actual_platform == "mt5":
        manager = get_manager()
        if manager.start_instance(account_id):
            return {"status": "connected", "account_id": account_id, "platform": "mt5"}
    elif actual_platform == "crypto":
        from src.live.crypto_connector import get_connector
        connector = get_connector(account_id)
        if connector and connector.connected:
            return {"status": "connected", "account_id": account_id, "platform": "crypto"}
    elif actual_platform == "tradovate":
        from src.live.tradovate_connector import get_tradovate_connector
        connector = get_tradovate_connector(account_id)
        if connector and connector.connected:
            return {"status": "connected", "account_id": account_id, "platform": "tradovate"}
    elif actual_platform == "nt8":
        manager = get_nt8_manager()
        account = manager.get_account(account_id)
        if account and os.path.exists(account.get("exchange_dir", "")):
             return {"status": "connected", "account_id": account_id, "platform": "nt8"}
        raise HTTPException(status_code=400, detail="Failed to connect to nt8 account. Exchange directory not found or inaccessible.")
    error_detail = "Check your API credentials or network connection."
    if not connector:
        error_detail = f"Failed to initialize {actual_platform} connector."
    elif not connector.connected:
        error_detail = "Connection failed (timeout or invalid keys)."
    raise HTTPException(status_code=400, detail=f"Failed to connect to {actual_platform} account. {error_detail}")
@router.get("/brokers")
async def get_brokers(type: str = Query("mt5")):
    try:
        logger.info(f"[ACCOUNTS] Fetching brokers for type: {type}")
        if type == "mt5":
            manager = get_manager()
            brokers = manager.get_broker_names()
            logger.info(f"[ACCOUNTS] Found {len(brokers)} MT5 brokers")
            return brokers
        elif type == "crypto":
            import ccxt
            # Priority/Verified exchanges that we have custom logic for
            verified = ["binance", "bybit", "okx", "bitget", "bingx", "blofin"]
            all_exchanges = set(ccxt.exchanges)
            
            # Combine verified (at top) with the rest of ccxt
            remaining = sorted(list(all_exchanges - set(verified)))
            exchanges = verified + remaining
            
            logger.info(f"[ACCOUNTS] Returning {len(exchanges)} crypto exchanges (verified first)")
            return exchanges
        elif type == "tradovate":
            return ["Tradovate"]
        elif type == "nt8":
            return ["NinjaTrader"]
        else:
            return []
    except Exception as e:
        logger.error(f"[ACCOUNTS] Error in get_brokers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{account_id}/leverage")
async def set_leverage_account(account_id: str, symbol: str = Body(...), leverage: int = Body(...), platform: str = Query("crypto")):
    if platform == "crypto":
        connector = get_connector(account_id)
        if not connector:
            raise HTTPException(status_code=503, detail="Connector not available")
        res = connector.set_leverage(symbol, leverage)
        if res.get("success"):
            return res
        error_msg = res.get("error", "Failed to set leverage")
        logger.error(f"[ACCOUNTS] Leverage error for {account_id}: {error_msg}")
        raise HTTPException(status_code=400, detail=f"Exchange error: {error_msg}")
    elif platform == "mt5":
        raise HTTPException(status_code=400, detail="Leverage adjustment via API not supported for MT5")
    else:
        raise HTTPException(status_code=400, detail=f"Leverage adjustment not supported for platform: {platform}")

@router.get("/server-search")
async def search_servers(q: str = Query(..., min_length=2)):
    try:
        logger.info(f"[ACCOUNTS] Searching servers for query: {q}")
        manager = get_manager()
        results = manager.search_servers(q)
        logger.info(f"[ACCOUNTS] Found {len(results)} match(es) for '{q}'")
        return results
    except Exception as e:
        logger.error(f"[ACCOUNTS] Error in search_servers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))