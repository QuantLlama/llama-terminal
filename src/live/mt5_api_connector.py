import requests
import pandas as pd
import logging
import time

logger = logging.getLogger(__name__)

class MT5ApiConnector:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MT5ApiConnector, cls).__new__(cls)
            cls._instance.base_url = kwargs.get("base_url", "http://127.0.0.1:8081")
            cls._instance.connected = False
        return cls._instance

    def __init__(self, base_url="http://127.0.0.1:8081"):
        if hasattr(self, 'initialized') and self.initialized: return
        self.host = "127.0.0.1"
        self.port = 8081
        self._ensure_server_running()
        self.initialized = True

    def _is_server_up(self):
        import socket
        try:
            with socket.create_connection((self.host, self.port), timeout=1):
                return True
        except OSError:
            return False

    def _ensure_server_running(self):
        if self._is_server_up():
            logger.info(f"MT5 Wine Server already running on port {self.port}")
            return
            
        logger.info("MT5 Wine Server not found. Launching automatically in background...")
        import platform
        import subprocess
        if "linux" in platform.system().lower():
            try:
                cmd = ["wine", "cmd.exe", "/c", "start_mt5_server.bat"]
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                logger.info("Waiting up to 15s for Wine to boot the MT5 server...")
                
                for i in range(15):
                    time.sleep(1)
                    if self._is_server_up():
                        logger.info("MT5 Wine Server is UP and ready!")
                        return
                logger.warning("MT5 Wine Server took too long to start. Check Wine.")
            except Exception as e:
                logger.error(f"Error launching wine server: {e}")
        
    def connect(self, path=None):
        try:
            res = requests.post(f"{self.base_url}/api/connect", json={"path": path}, timeout=5)
            self.connected = res.json().get("success", False)
            return self.connected
        except:
            return False

    def shutdown(self):
        try:
            requests.post(f"{self.base_url}/api/shutdown", timeout=2)
            self.connected = False
        except:
            pass

    def get_balance(self):
        try:
            return requests.get(f"{self.base_url}/api/balance").json().get("balance", 0.0)
        except:
            return 0.0

    def get_account_info(self):
        try:
            res = requests.get(f"{self.base_url}/api/account_info")
            if res.status_code == 200:
                return res.json()
        except:
            pass
        return None

    def get_equity(self):
        info = self.get_account_info()
        return info.get("equity", 0.0) if info else 0.0

    def get_latest_candles(self, symbol, timeframe="1m", n=100):
        try:
            res = requests.get(f"{self.base_url}/api/latest_candles/{symbol}?timeframe={timeframe}&n={n}")
            if res.status_code == 200:
                data = res.json()
                if not data: return None
                df = pd.DataFrame(data)
                if 'time' in df.columns:
                    df['time'] = pd.to_datetime(df['time'])
                return df
        except Exception as e:
            logger.error(f"API get_latest_candles error: {e}")
        return None

    def get_current_price(self, symbol):
        try:
            return requests.get(f"{self.base_url}/api/current_price/{symbol}").json().get("price", 0.0)
        except:
            return None

    def get_deals(self, date_from=None, date_to=None):
        try:
            url = f"{self.base_url}/api/deals?"
            if date_from: url += f"date_from={date_from.isoformat()}&"
            if date_to: url += f"date_to={date_to.isoformat()}"
            res = requests.get(url)
            if res.status_code == 200:
                data = res.json()
                from collections import namedtuple
                if not data: return []
                # Reconstruct namedtuple like objects for deals
                Result = namedtuple('TradeDeal', data[0].keys())
                return [Result(**d) for d in data]
        except Exception as e:
            logger.error(f"API get_deals error: {e}")
        return []

    def get_positions(self, symbol=None, ticket=None):
        try:
            url = f"{self.base_url}/api/positions?"
            if symbol: url += f"symbol={symbol}&"
            if ticket: url += f"ticket={ticket}"
            return requests.get(url).json()
        except:
            return []

    def get_pending_orders(self, symbol=None):
        try:
            url = f"{self.base_url}/api/pending_orders?"
            if symbol: url += f"symbol={symbol}"
            return requests.get(url).json()
        except:
            return []

    def place_order(self, symbol, order_type=None, volume=None, sl=None, tp=None, price=None, mode="MKT", **kwargs):
        side = kwargs.get('side')
        amount = kwargs.get('amount')
        try:
            res = requests.post(f"{self.base_url}/api/place_order", json={
                "symbol": symbol, "order_type": order_type, "volume": volume,
                "sl": sl, "tp": tp, "price": price, "mode": mode,
                "side": side, "amount": amount
            })
            if res.status_code == 200:
                data = res.json()
                from collections import namedtuple
                Result = namedtuple('OrderSendResult', data.keys())
                return Result(**data)
        except Exception as e:
            logger.error(f"API place_order error: {e}")
            pass
        return None

    def close_position(self, ticket, symbol=None, volume=None):
        try:
            url = f"{self.base_url}/api/close_position/{ticket}?"
            if symbol: url += f"symbol={symbol}&"
            if volume: url += f"volume={volume}"
            res = requests.post(url)
            if res.status_code == 200:
                 return True
        except:
            pass
        return False

    def get_daily_pnl(self):
        try:
            return requests.get(f"{self.base_url}/api/daily_pnl").json().get("pnl", 0.0)
        except:
            return 0.0

    def get_symbol_details(self, symbol):
        try:
             res = requests.get(f"{self.base_url}/api/symbol_details/{symbol}")
             if res.status_code == 200:
                 return res.json()
        except:
             pass
        return {"point": 0.0001, "digits": 5, "tick_size": 0.0001, "stops_level": 0, "broker_type": "cfd", "trade_exemode": -1}

_global_mt5_api_instance = None
def get_mt5_connector():
    global _global_mt5_api_instance
    if _global_mt5_api_instance is None:
        _global_mt5_api_instance = MT5ApiConnector()
    return _global_mt5_api_instance
