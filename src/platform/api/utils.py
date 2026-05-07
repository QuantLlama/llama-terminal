import os
import json
import math
from typing import List, Dict, Any, Optional
from src.utils.config_manager import load_symbol_map
CONFIG_FILE = "config.json"
def sanitize_float(data):
    if isinstance(data, float):
        if math.isnan(data) or math.isinf(data):
            return None
        return data
    elif isinstance(data, dict):
        return {k: sanitize_float(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_float(v) for v in data]
    return data

def sanitize_float_list(data_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Optimized non-recursive version for lists of flat dictionaries (candles)."""
    for item in data_list:
        if not isinstance(item, dict): continue
        for k, v in item.items():
            if isinstance(v, float):
                if math.isnan(v) or math.isinf(v):
                    item[k] = None
    return data_list
def resolve_symbol(symbol: str) -> str:
    platform = "mt5"
    if os.path.exists(CONFIG_FILE):
        pass
    symbol_map = load_symbol_map(platform)
    for cat in symbol_map:
        for sys_ticker, broker_ticker in symbol_map[cat].items():
            if sys_ticker == symbol:
                return broker_ticker
            sys_base = sys_ticker.split("=")[0]
            sym_base = symbol.split("=")[0]
            if sys_base == sym_base:
                return broker_ticker
            if broker_ticker == symbol:
                return broker_ticker
    return symbol