import sys
import os
import logging

logger = logging.getLogger(__name__)

USE_MT5_API = os.getenv("USE_MT5_API", "auto")

_global_instance = None

def get_mt5_connector():
    global _global_instance
    if _global_instance is not None:
        return _global_instance
        
    is_linux = sys.platform.startswith("linux")
    
    use_api = False
    if USE_MT5_API.lower() == "true":
        use_api = True
    elif USE_MT5_API.lower() == "auto" and is_linux:
        use_api = True
        
    if use_api:
        print("[FACTORY] System is Native Linux. Routing to MT5 API Connector...")
        from src.live.mt5_api_connector import MT5ApiConnector
        _global_instance = MT5ApiConnector()
    else:
        print("[FACTORY] System is Windows/Wine. Routing to MT5 Native Connector...")
        from src.live.mt5_native_connector import MT5Connector as NativeMT5Connector
        _global_instance = NativeMT5Connector()
        
    return _global_instance

MT5Connector = get_mt5_connector().__class__
