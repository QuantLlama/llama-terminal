import httpx
import pandas as pd
import numpy as np
import logging
import os
import time
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DEFAULT_BRIDGE_URL = "http://127.0.0.1:8081"


def resolve_bridge_url(explicit_url=None):
    """Explicit argument wins, then MT5_BRIDGE_URL, then the local bridge."""
    return explicit_url or os.getenv("MT5_BRIDGE_URL") or DEFAULT_BRIDGE_URL


def auto_launch_enabled():
    """Local Wine auto-launch stays on unless MT5_AUTO_LAUNCH disables it."""
    value = os.getenv("MT5_AUTO_LAUNCH", "true").strip().lower()
    return value not in {"false", "0", "no", "off"}


def bridge_headers():
    """Shared token header required by a network-exposed bridge."""
    token = os.getenv("MT5_BRIDGE_TOKEN", "").strip()
    return {"X-Bridge-Token": token} if token else None


class MT5ApiConnector:
    _instance = None
    
    # Constantes de MT5 necesarias para el bridge
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M10 = 10
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 16385
    TIMEFRAME_H4 = 16388
    TIMEFRAME_D1 = 16408
    COPY_TICKS_ALL = -1
    COPY_TICKS_INFO = 1
    COPY_TICKS_TRADE = 2
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MT5ApiConnector, cls).__new__(cls)
            cls._instance.base_url = resolve_bridge_url(kwargs.get("base_url"))
            cls._instance.connected = False
        return cls._instance

    def __init__(self, base_url=None):
        if hasattr(self, 'initialized') and self.initialized: return
        self.base_url = resolve_bridge_url(base_url)
        parsed = urlparse(self.base_url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(10.0, connect=5.0),
            # The token is attached per request, not frozen here: this connector is
            # instantiated while src/live/connector.py is imported, which happens
            # before load_dotenv() runs. Freezing the headers built a client with
            # no X-Bridge-Token and every connect() answered 401.
            event_hooks={"request": [self._attach_bridge_auth]},
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
        )
        if auto_launch_enabled():
            self._ensure_server_running()
        else:
            logger.info(f"MT5 bridge auto-launch disabled. Using {self.base_url}")
        self.initialized = True

    def _attach_bridge_auth(self, request):
        """Attach the shared bridge token as it exists for this request.

        Reading the environment here keeps the token correct even when the client
        was built before the configuration was loaded, and picks up a rotation
        without rebuilding the connector.
        """
        headers = bridge_headers()
        if headers:
            for name, value in headers.items():
                request.headers[name] = value

    #: A broker catalogue is thousands of symbols; keep it for a few minutes.
    _CATALOGUE_TTL_SECONDS = 600

    @staticmethod
    def _symbol_name(entry):
        if isinstance(entry, str):
            return entry
        if isinstance(entry, dict):
            return entry.get("name") or entry.get("symbol")
        return getattr(entry, "name", None)

    def _catalogue(self, force=False):
        """Names the broker currently lists, cached to avoid a call per request."""
        now = time.time()
        cached = getattr(self, "_catalogue_cache", None)
        if cached and not force and now - cached[0] < self._CATALOGUE_TTL_SECONDS:
            return cached[1]
        names = []
        for entry in self.symbols_get() or []:
            name = self._symbol_name(entry)
            if name:
                names.append(name)
        self._catalogue_cache = (now, names)
        return names

    def resolve_contract(self, symbol, force=False):
        """Resolve a futures root or an expired contract against the catalogue.

        A workspace saved months ago keeps asking for the contract that was
        current then; the broker drops it and the request answers "No history
        found". Anything that cannot be resolved is returned untouched.
        """
        if not symbol:
            return symbol
        try:
            catalogue = self._catalogue(force=force)
        except Exception as exc:
            logger.warning(f"Could not read the symbol catalogue: {exc}")
            return symbol
        if not catalogue:
            return symbol
        try:
            from src.utils.futures_contract import resolve_active_contract
            return resolve_active_contract(symbol, catalogue) or symbol
        except Exception as exc:
            logger.warning(f"Could not resolve the active contract for {symbol}: {exc}")
            return symbol

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
        
    def _bridge_client(self, timeout=None):
        """Bridge connection that always carries the shared token."""
        kwargs = {"base_url": self.base_url, "headers": bridge_headers()}
        if timeout is not None:
            kwargs["timeout"] = timeout
        return httpx.Client(**kwargs)

    def connect(self, path=None):
        try:
            res = self._client.post("/api/connect", json={"path": path})
            self.connected = res.json().get("success", False)
            return self.connected
        except Exception as e:
            logger.error(f"API connect error: {e}")
            return False

    def shutdown(self):
        """Release this client only; the bridge owns the MT5 session.

        Posting /api/shutdown here would tear down the Wine-side MT5 session
        for every other platform client on each request that finishes with a
        connector shutdown.
        """
        self.connected = False

    def shutdown_bridge(self):
        """Explicitly stop the remote bridge session (operator action)."""
        try:
            self._client.post("/api/shutdown", timeout=2.0)
        except Exception:
            pass
        self.connected = False

    def get_balance(self):
        try:
            return self._client.get("/api/balance").json().get("balance", 0.0)
        except:
            return 0.0

    def get_account_info(self):
        try:
            res = self._client.get("/api/account_info")
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
            res = self._client.get(f"/api/latest_candles/{symbol}?timeframe={timeframe}&n={n}", timeout=10.0)
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
            return self._client.get(f"/api/current_price/{symbol}").json().get("price", 0.0)
        except:
            return None

    def get_recent_ticks(self, symbol, n=1000):
        try:
            res = self._client.get(f"/api/recent_ticks/{symbol}?n={n}", timeout=2.0)
            if res.status_code == 200:
                data = res.json()
                if not data: return None
                return pd.DataFrame(data)
        except Exception as e:
            # Silently log timeout to avoid flooding console
            if "timed out" not in str(e).lower():
                logger.error(f"API get_recent_ticks error: {e}")
        return None

    def get_ticks_since(self, symbol, from_msc):
        try:
            res = self._client.get(f"/api/ticks_since/{symbol}?from_msc={from_msc}", timeout=2.0)
            if res.status_code == 200:
                data = res.json()
                if not data: return None
                return pd.DataFrame(data)
        except Exception as e:
            if "timed out" not in str(e).lower():
                logger.error(f"API get_ticks_since error: {e}")
        return None

    def get_book_snapshot(self, symbol, limit=100):
        try:
            res = self._client.get(f"/api/book_snapshot/{symbol}?limit={limit}", timeout=5.0)
            if res.status_code == 200:
                return res.json()
        except Exception as e:
            logger.error(f"API get_book_snapshot error: {e}")
        return None

    _SYMBOLS_TTL_SECONDS = 60.0

    def symbols_get(self, group=None, pattern=None):
        """Return symbols, filtered by the bridge and cached briefly.

        The catalogue can be ~1 MB over a tunnel, so filters are evaluated by
        the bridge and identical lookups are reused for a short window.
        """
        cache = getattr(self, "_symbols_cache", None)
        key = (group, pattern)
        now = time.monotonic()
        if cache and cache[0] == key and (now - cache[1]) < self._SYMBOLS_TTL_SECONDS:
            return cache[2]

        params = {}
        if group:
            params["group"] = group
        if pattern:
            params["pattern"] = pattern
        try:
            with self._bridge_client(timeout=90.0) as client:
                res = client.get("/api/symbols", params=params)
                data = res.json() if res.status_code == 200 else []
        except Exception as exc:
            logger.error(f"Symbol list error: {exc}")
            return cache[2] if cache and cache[0] == key else []

        symbols = [s for s in data if isinstance(s, dict)] if isinstance(data, list) else []
        self._symbols_cache = (key, now, symbols)
        return symbols

    def symbol_select(self, symbol, enable=True):
        try:
            res = self._client.post("/api/symbol_select", json={"symbol": symbol, "enable": enable}, timeout=3.0)
            return res.json().get("success", False)
        except:
            return False

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        try:
            res = self._client.get(f"/api/copy_rates_from_pos/{symbol}?timeframe={timeframe}&start_pos={start_pos}&count={count}", timeout=10.0)
            if res.status_code == 200:
                data = res.json()
                if not data: return None
                return np.array([tuple(d.values()) for d in data], dtype=[(k, 'f8') for k in data[0].keys()])
        except Exception as e:
            logger.error(f"API copy_rates_from_pos error: {e}")
        return None

    def copy_ticks_range(self, symbol, date_from, date_to, flags):
        try:
            ts_from = date_from.timestamp()
            ts_to = date_to.timestamp()
            res = self._client.get(f"/api/copy_ticks_range/{symbol}?date_from={ts_from}&date_to={ts_to}&flags={flags}", timeout=15.0)
            if res.status_code == 200:
                data = res.json()
                if not data: return None
                return np.array([tuple(d.values()) for d in data], dtype=[(k, 'f8') for k in data[0].keys()])
        except Exception as e:
            logger.error(f"API copy_ticks_range error: {e}")
        return None

    def get_deals(self, date_from=None, date_to=None):
        try:
            url = "/api/deals?"
            if date_from: url += f"date_from={date_from.isoformat()}&"
            if date_to: url += f"date_to={date_to.isoformat()}"
            with self._bridge_client() as client:
                res = client.get(url)
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
            url = "/api/positions?"
            if symbol: url += f"symbol={symbol}&"
            if ticket: url += f"ticket={ticket}"
            with self._bridge_client() as client:
                return client.get(url).json()
        except:
            return []

    def get_pending_orders(self, symbol=None):
        try:
            url = "/api/pending_orders?"
            if symbol: url += f"symbol={symbol}"
            with self._bridge_client() as client:
                return client.get(url).json()
        except:
            return []

    def place_order(self, symbol, order_type=None, volume=None, sl=None, tp=None, price=None, mode="MKT", **kwargs):
        side = kwargs.get('side')
        amount = kwargs.get('amount')
        try:
            with self._bridge_client() as client:
                res = client.post("/api/place_order", json={
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
            url = f"/api/close_position/{ticket}?"
            if symbol: url += f"symbol={symbol}&"
            if volume: url += f"volume={volume}"
            with self._bridge_client() as client:
                res = client.post(url)
                if res.status_code == 200:
                     return True
        except:
            pass
        return False

    def modify_position(self, ticket, sl, tp, symbol=None):
        try:
            with self._bridge_client() as client:
                res = client.post(f"/api/modify_position/{ticket}", json={
                    "sl": sl, "tp": tp, "symbol": symbol
                })
                if res.status_code == 200:
                    data = res.json()
                    from collections import namedtuple
                    Result = namedtuple('OrderSendResult', data.keys())
                    return Result(**data)
        except Exception as e:
            logger.error(f"API modify_position error: {e}")
        return None

    def modify_order(self, ticket, price=0.0, sl=0.0, tp=0.0):
        try:
            with self._bridge_client() as client:
                res = client.post(f"/api/modify_order/{ticket}", json={
                    "price": price, "sl": sl, "tp": tp
                })
                if res.status_code == 200:
                    data = res.json()
                    from collections import namedtuple
                    Result = namedtuple('OrderSendResult', data.keys())
                    return Result(**data)
        except Exception as e:
            logger.error(f"API modify_order error: {e}")
        return None

    def get_daily_pnl(self):
        try:
            with self._bridge_client() as client:
                return client.get("/api/daily_pnl").json().get("pnl", 0.0)
        except:
            return 0.0

    def symbol_info(self, symbol):
        """Full symbol record the bridge serves at /api/symbol_info.

        ``get_symbol_details`` only answers the few fields the chart needs; the
        order path also needs volume limits, so the raw record is fetched too.
        The bridge answers ``null`` when it does not know the symbol.
        """
        try:
            with self._bridge_client() as client:
                res = client.get(f"/api/symbol_info/{symbol}")
                if res.status_code == 200:
                    data = res.json()
                    return data if isinstance(data, dict) else None
        except Exception as e:
            logger.error(f"API symbol_info error: {e}")
        return None

    def get_symbol_details(self, symbol):
        try:
             with self._bridge_client() as client:
                res = client.get(f"/api/symbol_details/{symbol}")
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
