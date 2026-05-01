import requests
import logging
import time
import threading
from typing import Dict, List, Optional, Any
from datetime import datetime
logger = logging.getLogger(__name__)
class TradovateConnector:
    _instances = {}
    _lock = threading.RLock()
    def __new__(cls, account_id: str, username: str, password: str, 
               app_id: str, app_version: str, cid: str, sec: str, 
               environment: str = "demo"):
        with cls._lock:
            if account_id not in cls._instances:
                instance = super(TradovateConnector, cls).__new__(cls)
                instance._initialized = False
                cls._instances[account_id] = instance
            return cls._instances[account_id]
    def __init__(self, account_id: str, username: str, password: str, 
                 app_id: str, app_version: str, cid: str, sec: str, 
                 environment: str = "demo"):
        if self._initialized:
            return
        self.account_id = account_id
        self.username = username
        self.password = password
        self.app_id = app_id
        self.app_version = app_version
        self.cid = cid
        self.sec = sec
        self.environment = environment
        self.base_url = "https://demo.tradovateapi.com" if environment == "demo" else "https://live.tradovateapi.com"
        self.access_token = None
        self.token_expiry = 0
        self.connected = False
        self._initialized = True
        logger.info(f"TradovateConnector initialized for {username} (Account: {account_id}, Env: {environment})")
    def connect(self) -> bool:
        try:
            url = f"{self.base_url}/auth/accessTokenRequest"
            payload = {
                "name": self.username,
                "password": self.password,
                "appId": self.app_id,
                "appVersion": self.app_version,
                "cid": int(self.cid) if self.cid.isdigit() else self.cid,
                "sec": self.sec
            }
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get("accessToken")
                expiry_str = data.get("expirationTime")
                if expiry_str:
                    expiry_dt = datetime.strptime(expiry_str.replace("Z", ""), "%Y-%m-%dT%H:%M:%S.%f")
                    self.token_expiry = expiry_dt.timestamp()
                self.connected = True
                logger.info(f"Tradovate: Successfully authenticated for {self.username}")
                return True
            else:
                logger.error(f"Tradovate Auth Failed ({response.status_code}): {response.text}")
                self.connected = False
                return False
        except Exception as e:
            logger.error(f"Error connecting to Tradovate: {e}")
            self.connected = False
            return False
    def _ensure_token(self):
        if not self.access_token or time.time() > (self.token_expiry - 60):
            self.connect()
    def get_headers(self) -> Dict:
        self._ensure_token()
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    def get_balance(self) -> float:
        try:
            url = f"{self.base_url}/v1/cashBalance/list"
            response = requests.get(url, headers=self.get_headers())
            if response.status_code == 200:
                balances = response.json()
                return sum(b.get("amount", 0) for b in balances)
            return 0.0
        except Exception as e:
            logger.error(f"Tradovate Error get_balance: {e}")
            return 0.0
    def get_account_info(self) -> Optional[Dict]:
        try:
            url = f"{self.base_url}/v1/account/list"
            response = requests.get(url, headers=self.get_headers())
            if response.status_code == 200:
                accounts = response.json()
                if accounts:
                    acc = accounts[0]
                    return {
                        "balance": self.get_balance(),
                        "equity": 0.0, 
                        "account": acc.get("name"),
                        "name": acc.get("name"),
                        "server": self.environment.upper(),
                        "platform": "tradovate"
                    }
            return None
        except Exception as e:
            logger.error(f"Tradovate Error get_account_info: {e}")
            return None
    def get_tick(self, symbol: str) -> Dict:
        return {}
    def get_book_snapshot(self, symbol: str, limit: int = 50) -> Dict:
        return {"bids": [], "asks": [], "timestamp": 0}
    def place_order(self, symbol: str, side: str, volume: float, price: Optional[float] = None, mode: str = "MKT", **kwargs):
        try:
            return None
        except Exception as e:
            logger.error(f"Tradovate Error place_order: {e}")
            return None
GLOBAL_CONNECTORS: Dict[str, TradovateConnector] = {}
def get_tradovate_connector(account_id: str) -> Optional[TradovateConnector]:
    from src.services.tradovate_manager import get_tradovate_manager
    manager = get_tradovate_manager()
    acc = manager.get_account_full(account_id)
    if not acc:
        return None
    if account_id in GLOBAL_CONNECTORS:
        return GLOBAL_CONNECTORS[account_id]
    try:
        connector = TradovateConnector(
            account_id=account_id,
            username=acc['username'],
            password=acc['password'],
            app_id=acc['app_id'],
            app_version=acc['app_version'],
            cid=str(acc['cid']),
            sec=acc['sec'],
            environment=acc.get('environment', 'demo')
        )
        if connector.connect():
            GLOBAL_CONNECTORS[account_id] = connector
            return connector
    except Exception as e:
        logger.error(f"Failed to create Tradovate connector for {account_id}: {e}")
    return None