"""
Backtesting API Router for Quantum Llama Terminal.
Integrates the Algoritest backtesting engine into the platform.
"""
import asyncio
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import io

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from fastapi import APIRouter, Body, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ReportLab imports
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine directory (migrated from Algoritest)
# ---------------------------------------------------------------------------
_ENGINE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "engine")
)

router = APIRouter(prefix="/api/backtest", tags=["backtesting"])

# ---------------------------------------------------------------------------
# Global state for long-running operations
# ---------------------------------------------------------------------------
_backtest_state = {
    "loaded_data": None,          # pandas DataFrame (or None)
    "loaded_data_info": None,     # metadata dict
    "last_results": None,         # last backtest result dict
    "optimizer_job": None,        # optimizer status dict
    "logs": [],                   # log lines for the terminal
}

MAX_LOGS = 500

def _add_log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    _backtest_state["logs"].append(line)
    if len(_backtest_state["logs"]) > MAX_LOGS:
        _backtest_state["logs"] = _backtest_state["logs"][-MAX_LOGS:]
    logger.info(msg)


def _safe_float(val: Any) -> Optional[float]:
    """Ensure a value is JSON-serializable (no NaN/Inf)."""
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return 0.0
        return f
    except (TypeError, ValueError):
        return 0.0


def _sanitize_dict(obj: Any) -> Any:
    """Recursively replace NaN/Inf with None in a dict/list."""
    if isinstance(obj, dict):
        return {k: _sanitize_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_dict(x) for x in obj]
    elif isinstance(obj, (float, np.floating)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif pd.isna(obj): # Catch Timestamp NaT or other pandas nulls
        return None
    return obj


def _get_duration_str(start: Any, end: Any) -> str:
    """Format the simulation duration in years, months, and days."""
    try:
        from datetime import datetime
        if isinstance(start, str): start = pd.to_datetime(start)
        if isinstance(end, str): end = pd.to_datetime(end)
        
        diff = end - start
        years = diff.days // 365
        months = (diff.days % 365) // 30
        days = (diff.days % 365) % 30
        
        parts = []
        if years > 0: parts.append(f"{years}y")
        if months > 0: parts.append(f"{months}m")
        if days > 0: parts.append(f"{days}d")
        return " ".join(parts) if parts else f"{diff.days}d"
    except Exception:
        return "N/A"

class ApiLogHandler(logging.Handler):
    """Redirects engine logs to the platform's _add_log system."""
    def emit(self, record):
        msg = self.format(record)
        if "Iniciando backtesting" in msg: return # Too spammy
        _add_log(msg)


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class LoadDataRequest(BaseModel):
    source: str  # "yahoo", "csv", "mt5"
    symbol: str = "AAPL"
    period: str = "2y"
    csv_path: Optional[str] = None
    timeframe: str = "1d"
    days: int = 90


class BacktestRunRequest(BaseModel):
    strategy_name: str = "StrategyOrderFlow"
    strategy_params: Optional[Dict[str, Any]] = None
    initial_balance: float = 10000.0
    tick_size: float = 0.25
    tick_value: float = 0.5
    # Professional Execution Controls
    max_trades_per_day: Optional[int] = None
    # Date Filtering
    from_date: Optional[str] = None # YYYY-MM-DD
    to_date: Optional[str] = None   # YYYY-MM-DD
    start_hour: Optional[int] = None # 0-23
    end_hour: Optional[int] = None   # 0-23
    ignore_filters: bool = False     # Manual override for all execution filters
    sl_override: Optional[float] = None
    tp_override: Optional[float] = None


class OptimizeRequest(BaseModel):
    strategy_name: str = "StrategyOrderFlow"
    population_size: int = 30
    generations: int = 10
    crossover_rate: float = 0.8
    mutation_rate: float = 0.07
    initial_balance: float = 10000.0
    tick_size: float = 0.25
    tick_value: float = 0.5
    # Professional Execution Controls
    max_trades_per_day: Optional[int] = None
    # Date Filtering
    from_date: Optional[str] = None # YYYY-MM-DD
    to_date: Optional[str] = None   # YYYY-MM-DD
    start_hour: Optional[int] = None # 0-23
    end_hour: Optional[int] = None   # 0-23
    ignore_filters: bool = False     # Manual override for all execution filters
    sl_override: Optional[float] = None
    tp_override: Optional[float] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/strategies")
async def list_strategies():
    """List available strategies and their configurable parameters from platform."""
    try:
        from src.algorithms import list_algorithms
        algos = list_algorithms()
        
        strategies = []
        for k, v in algos.items():
            parameters = {}
            for pk, pv in v.get('config_schema', {}).items():
                parameters[pk] = {
                    "value": pv.get('default', 0),
                    "type": pv.get('type', 'float'),
                    "description": pk.replace('_', ' ').title()
                }
            strategies.append({
                "id": k,
                "name": v['name'],
                "description": v['description'],
                "parameters": parameters,
            })
            
        return {"strategies": strategies}
    except Exception as e:
        logger.error(f"Error listing strategies: {e}")
        return {"strategies": [], "error": str(e)}

class PlatformStrategyAdapter:
    def __init__(self, strategy_params):
        if isinstance(strategy_params, dict) and 'algo_instance' in strategy_params:
            self.algo = strategy_params['algo_instance']
            self.params = strategy_params.get('params', {})
            
            # 1. Dynamic Reconstruction (Critical for Optimizer)
            # If algo is None but we have a name, instantiate it now
            if self.algo is None and '_algo_name' in self.params:
                from src.algorithms import get_algorithm
                self.algo = get_algorithm(self.params['_algo_name'], config=self.params)
                if self.algo:
                    logger.info(f"PlatformStrategyAdapter: Lazy-loaded strategy {self.params['_algo_name']}")
                else:
                    logger.error(f"PlatformStrategyAdapter: FAILED to lazy-load strategy {self.params['_algo_name']}")
        else:
            # Fallback for manual or legacy instantiation
            self.algo = strategy_params
            self.params = {}
            if self.algo is None:
                logger.warning("PlatformStrategyAdapter: Initialized with self.algo = None (fallback)")
            
        # 2. Extract Professional Constraints
        self.max_trades = self.params.get('max_trades_per_day')
        self.start_hour = self.params.get('start_hour')
        self.end_hour = self.params.get('end_hour')
        self.ignore_filters = self.params.get('ignore_filters', False)
        
        self.sl_override = self.params.get('sl_override')
        self.tp_override = self.params.get('tp_override')
        self.tick_size = self.params.get('tick_size', 0.25) # Default tick size if not provided
        
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        import pandas as pd
        import numpy as np
        
        # 0. Ensure we have a DatetimeIndex at the very beginning
        # This is critical for hour filtering and consistent copy/slicing
        data = data.copy()
        if not isinstance(data.index, pd.DatetimeIndex):
            ts_col = next((c for c in data.columns if c.lower() in ['timestamp', 'time']), None)
            if ts_col:
                first_val = data[ts_col].iloc[0]
                unit = None
                if isinstance(first_val, (int, float, np.integer)):
                    unit = 's' if first_val < 1e11 else 'ms' if first_val < 1e14 else 'ns'
                
                if data[ts_col].dtype != 'datetime64[ns]':
                    data[ts_col] = pd.to_datetime(data[ts_col], unit=unit)
                data.set_index(ts_col, inplace=True)
            else:
                try:
                    first_val = data.index[0]
                    unit = None
                    if isinstance(first_val, (int, float, np.integer)):
                        unit = 's' if first_val < 1e11 else 'ms' if first_val < 1e14 else 'ns'
                    data.index = pd.to_datetime(data.index, unit=unit)
                except:
                    logger.warning("Could not convert index to DatetimeIndex in PlatformStrategyAdapter")

        # Create a copy with standardized columns to support all strategy types
        algo_data = data.copy()
        
        # 1. Expand Column Mapping (High compatibility mode)
        col_mapping = {
            'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume',
            'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume',
            'TickVolume': 'volume', 'tick_volume': 'volume', 'RealVolume': 'volume',
            'Close': 'last', 'close': 'last'
        }
        for src, dst in col_mapping.items():
            if src in algo_data.columns and dst not in algo_data.columns:
                algo_data[dst] = algo_data[src]
        
        # 2. Add Direction and Normalize Case
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in algo_data.columns:
                title_col = col.capitalize()
                if title_col not in algo_data.columns:
                    algo_data[title_col] = algo_data[col]

        if 'direction' not in algo_data.columns and 'close' in algo_data.columns and 'open' in algo_data.columns:
            algo_data['direction'] = np.where(algo_data['close'] > algo_data['open'], 1, 
                                             np.where(algo_data['close'] < algo_data['open'], -1, 0))
        
        # 3. Proactive Indicator Calculation (ATR / RSI / EMA)
        # These are automatically calculated to guarantee compatibility with ALL strategies.
        if 'Close' in algo_data.columns:
            c = algo_data['Close']

            # ATR (14)
            if 'ATR' not in algo_data.columns:
                try:
                    high = algo_data.get('High', c)
                    low = algo_data.get('Low', c)
                    tr = pd.concat([high - low,
                                    (high - c.shift()).abs(),
                                    (low - c.shift()).abs()], axis=1).max(axis=1)
                    algo_data['ATR'] = tr.rolling(window=14).mean()
                except Exception: pass

            # RSI (14) — required by FourierCycleStrategy
            if 'RSI' not in algo_data.columns:
                try:
                    delta = c.diff()
                    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
                    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
                    rs = gain / (loss + 1e-10)
                    algo_data['RSI'] = 100 - (100 / (1 + rs))
                except Exception: pass

            # EMA_Fast (8) and EMA_Slow (21) — required by FourierCycleStrategy
            if 'EMA_Fast' not in algo_data.columns:
                try:
                    algo_data['EMA_Fast'] = c.ewm(span=8, adjust=False).mean()
                except Exception: pass

            if 'EMA_Slow' not in algo_data.columns:
                try:
                    algo_data['EMA_Slow'] = c.ewm(span=21, adjust=False).mean()
                except Exception: pass


        signals = data.copy()
        sig_arr = np.zeros(len(data))
        sl_arr = np.full(len(data), np.nan)
        tp_arr = np.full(len(data), np.nan)
        
        error_count = 0
        last_error = ""
        
        # State for trade limits
        trades_today = 0
        last_date = None
        last_active_sig = 0
        had_hold_gap = True # Used to distinguish new signals from streaks
        
        filtered_by_hour = 0
        filtered_by_limit = 0
        
        # Professional standard: Passing enough history for ML/Indicators (up to 1500 bars)
        for i in range(len(data)):
            current_time = data.index[i]
            current_date = current_time.date()
            
            # Reset daily trade counter
            if current_date != last_date:
                trades_today = 0
                last_date = current_date
            
            # 1. Hour Filter
            if self.start_hour is not None and self.end_hour is not None:
                hour = current_time.hour
                if not (self.start_hour <= hour <= self.end_hour):
                    filtered_by_hour += 1
                    continue
            
            # 2. Daily Limit Filter
            if self.max_trades is not None and trades_today >= self.max_trades:
                filtered_by_limit += 1
                continue

            # Provide sliding window history
            window = algo_data.iloc[max(0, i-1500) : i+1].copy()
            if len(window) < 2: 
                continue
            
            if self.algo is None:
                raise ValueError(f"Strategy instance 'algo' is None. Initialization failed for strategy parameters: {self.params}")

            try:
                # Most strategies return (signal, metadata)
                res = self.algo.update(window)
                
                # Robust return handling
                if isinstance(res, tuple):
                    sig_str = res[0]
                    meta = res[1] if len(res) > 1 else {}
                elif isinstance(res, dict):
                    sig_str = res.get('signal', 'HOLD')
                    meta = res
                else:
                    sig_str = str(res)
                    meta = {}
                
                s_val = 0
                if sig_str in ['BUY', '1', 'LONG']: s_val = 1
                elif sig_str in ['SELL', '-1', 'SHORT']: s_val = -1
                
                if s_val != 0:
                    # Logic: Record signal if it's a reversal OR if we had a HOLD gap since the last signal
                    # This prevents streaking signals from being counted as 100 separate trades
                    if s_val != last_active_sig or had_hold_gap:
                        # 3. Apply Filters ONLY if NOT ignored
                        is_filtered = False
                        if not self.ignore_filters:
                            # Hour Filter Check
                            if self.start_hour is not None and self.end_hour is not None:
                                hour = current_time.hour
                                if not (self.start_hour <= hour <= self.end_hour):
                                    filtered_by_hour += 1
                                    is_filtered = True
                            
                            # Daily Limit Check
                            if not is_filtered and self.max_trades is not None and trades_today >= self.max_trades:
                                filtered_by_limit += 1
                                is_filtered = True
                        
                        if not is_filtered:
                            sig_arr[i] = s_val
                            trades_today += 1
                            last_active_sig = s_val
                            had_hold_gap = False
                        else:
                            # Even if filtered by risk/time, we mark it as 'gap' to allow future signals 
                            # when conditions permit.
                            had_hold_gap = True
                else:
                    had_hold_gap = True # Signal reset gap detected
                    
                if isinstance(meta, dict):
                    # Try various metadata keys for SL/TP
                    sl = meta.get('stop_loss_price') or meta.get('sl') or meta.get('stop_loss')
                    tp = meta.get('take_profit_price') or meta.get('tp') or meta.get('take_profit')
                    if sl is not None: sl_arr[i] = float(sl)
                    if tp is not None: tp_arr[i] = float(tp)
                    
            except Exception as e:
                error_count += 1
                last_error = str(e)
                if error_count < 3: # Log only first few errors to avoid spam
                     logger.warning(f"Strategy update error at bar {i}: {e}")
                
        if error_count > 0:
            _add_log(f"⚠️ Warning: Strategy had {error_count} errors during signal generation. Last error: {last_error}")

        # Diagnostic summary
        total_signals = int(np.sum(np.abs(sig_arr)))
        _add_log(f"📊 Signal Diagnostic: Total={total_signals}, FilteredByHour={filtered_by_hour}, FilteredByLimit={filtered_by_limit}")
        if total_signals == 0 and filtered_by_hour > 0:
            _add_log(f"💡 Tip: Many signals ({filtered_by_hour}) were filtered by your Hour Constraint. Check your Session Hours!")

        signals['signal'] = sig_arr
        signals['stop_loss'] = sl_arr
        signals['take_profit'] = tp_arr
        return signals

    def check_entry_conditions(self, current_data, signal):
        return True
        
    def calculate_exit_levels(self, entry_price, direction, atr=None):
        # 1. Start with strategy defaults (if any) or fallback logic
        if hasattr(self.algo, 'calculate_exit_levels'):
            levels = self.algo.calculate_exit_levels(entry_price, direction, atr)
            sl = levels.get('stop_loss')
            tp = levels.get('take_profit')
        else:
            sl = entry_price - 25 * self.tick_size if direction.upper() == 'LONG' else entry_price + 25 * self.tick_size
            tp = entry_price + 50 * self.tick_size if direction.upper() == 'LONG' else entry_price - 50 * self.tick_size
            
        # 2. Apply Global Overrides if defined
        if getattr(self, 'sl_override', None) is not None:
            offset = self.sl_override * self.tick_size
            sl = entry_price - offset if direction.upper() == 'LONG' else entry_price + offset
            
        if getattr(self, 'tp_override', None) is not None:
            offset = self.tp_override * self.tick_size
            tp = entry_price + offset if direction.upper() == 'LONG' else entry_price - offset
            
        return {'stop_loss': sl, 'take_profit': tp}

    def should_exit(self, current_price, position, entry_time=None):
        direction = position.get('direction')
        stop_loss = position.get('stop_loss')
        take_profit = position.get('take_profit')
        if direction.upper() == 'LONG':
            if stop_loss is not None and pd.notna(stop_loss) and current_price <= stop_loss: return 'STOP_LOSS'
            if take_profit is not None and pd.notna(take_profit) and current_price >= take_profit: return 'TAKE_PROFIT'
        else:
            if stop_loss is not None and pd.notna(stop_loss) and current_price >= stop_loss: return 'STOP_LOSS'
            if take_profit is not None and pd.notna(take_profit) and current_price <= take_profit: return 'TAKE_PROFIT'
        return None


@router.get("/indicators")
async def list_bt_indicators():
    """List available order-flow indicators from Algoritest."""
    try:
        return {
            "indicators": [
                {"id": "delta", "name": "Delta", "functions": ["calculate_delta", "cumulative_delta", "delta_divergence", "aggressive_buying_pressure", "aggressive_selling_pressure", "delta_momentum"]},
                {"id": "volume_profile", "name": "Volume Profile", "functions": ["volume_profile", "vah_val", "poc", "tpo_profile", "volume_at_price"]},
                {"id": "imbalance", "name": "Imbalance", "functions": ["detect_imbalance", "absorption_detection", "resting_orders_detection", "order_book_depth"]},
                {"id": "price_action", "name": "Price Action", "functions": ["detect_key_levels", "detect_rejection_candles", "detect_engulfing", "market_structure", "vwap"]},
            ]
        }
    except Exception as e:
        return {"indicators": [], "error": str(e)}


@router.get("/data/sources")
async def list_data_sources():
    """List available data sources."""
    return {
        "sources": [
            {"id": "yahoo", "name": "Yahoo Finance", "description": "Free historical data for stocks, ETFs, futures, crypto", "icon": "fa-chart-line"},
            {"id": "csv", "name": "CSV File", "description": "Load your own CSV with OHLCV data", "icon": "fa-file-csv"},
            {"id": "mt5", "name": "MetaTrader 5", "description": "Real-time and historical data from MT5 (requires MT5 running)", "icon": "fa-chart-bar"},
        ]
    }


@router.post("/data/load")
async def load_data(req: LoadDataRequest):
    """Load historical data from a specified source."""
    _add_log(f"Loading data: source={req.source}, symbol={req.symbol}")

    try:
        import pandas as pd
        import numpy as np

        df = None

        if req.source == "yahoo":
            try:
                import yfinance as yf
                _add_log(f"Downloading from Yahoo Finance: {req.symbol} period={req.period}")
                data = yf.download(req.symbol, period=req.period, progress=False)
                if data is None or len(data) == 0:
                    raise ValueError(f"No data returned for {req.symbol}")

                data.reset_index(inplace=True)

                # Handle multi-level columns from yfinance
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = [c[0] if isinstance(c, tuple) else c for c in data.columns]

                rename_map = {}
                for col in data.columns:
                    cl = str(col).lower().strip()
                    if cl in ('date', 'datetime', 'timestamp'):
                        rename_map[col] = 'timestamp'
                    elif cl == 'open':
                        rename_map[col] = 'open'
                    elif cl == 'high':
                        rename_map[col] = 'high'
                    elif cl == 'low':
                        rename_map[col] = 'low'
                    elif cl == 'close':
                        rename_map[col] = 'close'
                    elif cl in ('volume', 'vol'):
                        rename_map[col] = 'volume'

                data.rename(columns=rename_map, inplace=True)

                for needed in ['open', 'high', 'low', 'close', 'volume']:
                    if needed not in data.columns:
                        raise ValueError(f"Missing column: {needed}")

                data['spread'] = 0
                data['real_volume'] = data['volume']
                data['last'] = data['close']
                data['direction'] = np.where(data['close'] > data['open'], 1, np.where(data['close'] < data['open'], -1, 0))

                df = data
                _add_log(f"Yahoo data loaded: {len(df)} candles")

            except ImportError:
                raise HTTPException(status_code=500, detail="yfinance not installed. Run: pip install yfinance")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Yahoo Finance error: {str(e)}")

        elif req.source == "csv":
            try:
                if not req.csv_path:
                    # Check default engine data path
                    default_csv = os.path.join(_ENGINE_DIR, "data", "historical_mnq.csv")
                    if os.path.exists(default_csv):
                        req.csv_path = default_csv
                    else:
                        raise HTTPException(status_code=400, detail="No CSV path provided and no default data found")

                if not os.path.exists(req.csv_path):
                    raise HTTPException(status_code=404, detail=f"CSV file not found: {req.csv_path}")

                df = pd.read_csv(req.csv_path)
                if 'last' not in df.columns and 'close' in df.columns:
                    df['last'] = df['close']
                if 'direction' not in df.columns:
                    df['direction'] = np.where(df['close'] > df['open'], 1, np.where(df['close'] < df['open'], -1, 0))
                _add_log(f"CSV data loaded: {len(df)} rows from {req.csv_path}")
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"CSV load error: {str(e)}")

        elif req.source == "mt5":
            try:
                import MetaTrader5 as mt5
                if not mt5.initialize():
                    raise HTTPException(status_code=500, detail="Could not initialize MT5")

                tf_map = {
                    "1m": mt5.TIMEFRAME_M1, "5m": mt5.TIMEFRAME_M5,
                    "15m": mt5.TIMEFRAME_M15, "30m": mt5.TIMEFRAME_M30,
                    "1h": mt5.TIMEFRAME_H1, "4h": mt5.TIMEFRAME_H4,
                    "1d": mt5.TIMEFRAME_D1,
                }
                mt5_tf = tf_map.get(req.timeframe, mt5.TIMEFRAME_M1)
                rates = mt5.copy_rates_from_pos(req.symbol, tf_map.get(req.timeframe, mt5.TIMEFRAME_M1), 0, req.days * 1440)
                if rates is None or len(rates) == 0:
                    raise HTTPException(status_code=400, detail=f"No data returned from MT5 for {req.symbol} on {req.timeframe}")

                df = pd.DataFrame(rates)
                df['timestamp'] = pd.to_datetime(df['time'], unit='s')
                df.rename(columns={'tick_volume': 'volume'}, inplace=True)
                if 'last' not in df.columns:
                    df['last'] = df['close']
                if 'direction' not in df.columns:
                    df['direction'] = np.where(df['close'] > df['open'], 1, np.where(df['close'] < df['open'], -1, 0))
                _add_log(f"MT5 data loaded: {len(df)} candles for {req.symbol}")

            except ImportError:
                raise HTTPException(status_code=500, detail="MetaTrader5 not available")
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"MT5 error: {str(e)}")
        else:
            raise HTTPException(status_code=400, detail=f"Unknown source: {req.source}")

        # Standardize: Ensure timestamp is the index
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
        elif not isinstance(df.index, pd.DatetimeIndex):
            try:
                df.index = pd.to_datetime(df.index)
            except:
                pass

        # Store in memory
        _backtest_state["loaded_data"] = df
        _backtest_state["loaded_data_info"] = {
            "source": req.source,
            "symbol": req.symbol,
            "rows": len(df),
            "columns": list(df.columns),
            "date_range": {
                "start": str(df.index.min()) if hasattr(df.index, 'min') else "N/A",
                "end": str(df.index.max()) if hasattr(df.index, 'max') else "N/A",
            },
            "loaded_at": datetime.now().isoformat(),
        }

        _add_log(f"Data ready: {len(df)} records for {req.symbol}")

        # Return summary (not all data)
        resp = {
            "status": "ok",
            "info": _backtest_state["loaded_data_info"],
            "preview": {
                "first_5": df.head(5).to_dict(orient="records"),
                "last_5": df.tail(5).to_dict(orient="records"),
                "stats": {
                    "open_min": _safe_float(df["open"].min()),
                    "open_max": _safe_float(df["open"].max()),
                    "close_min": _safe_float(df["close"].min()),
                    "close_max": _safe_float(df["close"].max()),
                    "volume_mean": _safe_float(df["volume"].mean()),
                    "volume_max": _safe_float(df["volume"].max()),
                },
            }
        }
        return _sanitize_dict(resp)

    except HTTPException:
        raise
    except Exception as e:
        _add_log(f"ERROR loading data: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data/upload_raw_csv")
async def upload_raw_csv(request: Request, filename: str = "custom.csv"):
    """Accept raw CSV text upload without writing to disk temporarily."""
    try:
        body = await request.body()
        import io
        import pandas as pd
        import numpy as np

        text_content = body.decode("utf-8")
        _add_log(f"Processing uploaded CSV: {filename} ({len(text_content)} chars)")
        
        df = pd.read_csv(io.StringIO(text_content))

        if 'last' not in df.columns and 'close' in df.columns:
            df['last'] = df['close']
        if 'direction' not in df.columns and 'close' in df.columns and 'open' in df.columns:
            df['direction'] = np.where(df['close'] > df['open'], 1, np.where(df['close'] < df['open'], -1, 0))
            
        _backtest_state["loaded_data"] = df
        if df is not None:
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
            _backtest_state["loaded_data"] = df

        _backtest_state["loaded_data_info"] = {
            "source": f"csv: {filename}",
            "symbol": "CUSTOM_CSV",
            "rows": len(df),
            "columns": list(df.columns),
            "date_range": {
                "start": str(df.index.min()) if hasattr(df.index, 'min') else "N/A",
                "end": str(df.index.max()) if hasattr(df.index, 'max') else "N/A",
            },
            "loaded_at": datetime.now().isoformat(),
        }
        
        _add_log(f"CSV data ready: {len(df)} records from {filename}")
        
        return {
            "status": "success",
            "records": len(df),
            "filename": filename
        }
    except Exception as e:
        _add_log(f"ERROR uploading raw CSV: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/data/validate")
async def validate_data():
    """Validate the currently loaded dataset."""
    df = _backtest_state.get("loaded_data")
    if df is None:
        raise HTTPException(status_code=400, detail="No data loaded. Load data first.")

    import numpy as np

    issues = []
    warnings = []

    # Check required columns
    required = ['open', 'high', 'low', 'close', 'volume']
    for col in required:
        if col not in df.columns:
            issues.append(f"Missing required column: {col}")

    if not issues:
        # Check for NaN values
        nan_counts = df[required].isna().sum()
        for col, count in nan_counts.items():
            if count > 0:
                warnings.append(f"Column '{col}' has {count} NaN values ({count/len(df)*100:.1f}%)")

        # Check for zero volume
        zero_vol = (df['volume'] == 0).sum()
        if zero_vol > len(df) * 0.5:
            warnings.append(f"{zero_vol} rows ({zero_vol/len(df)*100:.1f}%) have zero volume")

        # Check OHLC consistency
        ohlc_errors = ((df['high'] < df['low']) | (df['high'] < df['open']) | (df['high'] < df['close']) |
                       (df['low'] > df['open']) | (df['low'] > df['close'])).sum()
        if ohlc_errors > 0:
            issues.append(f"{ohlc_errors} rows have inconsistent OHLC values")

        # Check for duplicates
        if 'timestamp' in df.columns:
            dup_count = df['timestamp'].duplicated().sum()
            if dup_count > 0:
                warnings.append(f"{dup_count} duplicate timestamps found")

    valid = len(issues) == 0
    _add_log(f"Data validation: {'PASSED' if valid else 'FAILED'} - {len(issues)} issues, {len(warnings)} warnings")

    return {
        "valid": valid,
        "total_rows": len(df),
        "issues": issues,
        "warnings": warnings,
        "from_date": str(df.index.min()) if hasattr(df.index, 'min') else None,
        "to_date": str(df.index.max()) if hasattr(df.index, 'max') else None,
    }


@router.post("/run")
async def run_backtest(req: BacktestRunRequest):
    """Execute a backtest with the loaded data and given parameters."""
    df = _backtest_state.get("loaded_data")
    if df is None:
        raise HTTPException(status_code=400, detail="No data loaded. Load data first.")

    # -----------------------------------------------------------------------
    # 2. Date Filtering (Professional Crop)
    # -----------------------------------------------------------------------
    if req.from_date or req.to_date:
        try:
            import pandas as pd
            if req.from_date:
                df = df[df.index >= pd.to_datetime(req.from_date)]
            if req.to_date:
                df = df[df.index <= pd.to_datetime(req.to_date)]
            _add_log(f"[BACKTEST] Data cropped to range: {df.index.min()} to {df.index.max()}")
        except Exception as e:
            _add_log(f"[WARNING] Date filtering failed: {e}")

    if len(df) < 2:
        raise HTTPException(status_code=400, detail="Insufficient data for backtest after date filtering.")

    _add_log("Starting backtest execution...")

    try:
        from src.engine.backtesting.backtester import Backtester
        from src.engine.backtesting.metrics import calculate_trading_metrics, generate_trade_report
        from src.algorithms import list_algorithms, get_algorithm

        # We need to map algorithm name to the key from list_algorithms
        algos = list_algorithms()
        algo_id = req.strategy_name
        for k, v in algos.items():
            if v['name'] == req.strategy_name:
                algo_id = k
                break
        
        # Instantiate the actual algorithm
        algo_instance = get_algorithm(algo_id, config=req.strategy_params)

        # Merge controls into params for the strategy adapter
        params = req.strategy_params or {}
        params['max_trades_per_day'] = req.max_trades_per_day
        params['start_hour'] = req.start_hour
        params['end_hour'] = req.end_hour
        params['ignore_filters'] = req.ignore_filters
        params['_algo_name'] = algo_id

        backtester = Backtester(
            df, 
            initial_balance=req.initial_balance, 
            strategy_class=PlatformStrategyAdapter,
            tick_size=req.tick_size,
            tick_value=req.tick_value
        )

        # Run the backtest in a thread to avoid blocking
        loop = asyncio.get_event_loop()
        strat_params = {'algo_instance': algo_instance, 'params': params}
        metrics = await loop.run_in_executor(
            None, lambda: backtester.run(strategy_params=strat_params)
        )

        # Calculate extended metrics
        extended_metrics = calculate_trading_metrics(
            backtester.trades, backtester.equity_curve, req.initial_balance
        )

        # Generate text report
        report = generate_trade_report(backtester.trades, extended_metrics)

        # Subsample equity curve for frontend (max 500 points)
        equity = backtester.equity_curve
        if len(equity) > 500:
            step = len(equity) // 500
            equity_sampled = equity[::step]
        else:
            equity_sampled = equity

        # Calculate drawdown series
        import numpy as np
        import pandas as pd
        eq_series = pd.Series(equity_sampled)
        max_eq = eq_series.cummax()
        drawdown = ((max_eq - eq_series) / max_eq * 100).fillna(0).tolist()

        # Format trades for frontend
        trades_data = []
        for i, t in enumerate(backtester.trades):
            entry_t = t.get("entry_time")
            exit_t = t.get("exit_time")
            
            # Simple duration calc
            duration_val = "--"
            if isinstance(entry_t, pd.Timestamp) and isinstance(exit_t, pd.Timestamp):
                diff = exit_t - entry_t
                duration_val = str(diff).split('.')[0] # Remove microseconds

            trades_data.append({
                "id": i + 1,
                "type": t.get("direction", ""), # Frontend expects 'type'
                "direction": t.get("direction", ""), # Backward compatibility
                "entry_price": round(t.get("entry_price", 0), 4),
                "exit_price": round(t.get("exit_price", 0), 4),
                "entry_time": str(entry_t) if entry_t else "--",
                "exit_time": str(exit_t) if exit_t else "--",
                "duration": duration_val,
                "pnl": round(t.get("pnl", 0), 2),
                "exit_reason": t.get("exit_reason", ""),
                "contracts": t.get("contracts", 1),
            })

        # PnL distribution for histogram
        pnls = [t["pnl"] for t in trades_data]
        pnl_dist = []
        if pnls:
            min_pnl = min(pnls)
            max_pnl = max(pnls)
            if min_pnl != max_pnl:
                bin_count = min(30, len(pnls))
                bin_width = (max_pnl - min_pnl) / bin_count
                for b in range(bin_count):
                    low = min_pnl + b * bin_width
                    high = low + bin_width
                    count = sum(1 for p in pnls if low <= p < high) if b < bin_count - 1 else sum(1 for p in pnls if low <= p <= high)
                    pnl_dist.append({"low": round(low, 2), "high": round(high, 2), "count": count})

        # Sample timestamps same way as equity
        all_ts = df['timestamp'].tolist() if 'timestamp' in df.columns else []
        if len(all_ts) > 500:
            ts_sampled = all_ts[::step]
        else:
            ts_sampled = all_ts
            
        # Limit to equity curve length (sometimes they differ by 1 or 2 due to warm-up)
        ts_sampled = ts_sampled[:len(equity_sampled)]
        
        duration_str = "N/A"
        if all_ts:
            duration_str = _get_duration_str(all_ts[0], all_ts[-1])

        # Store in state
        results = _sanitize_dict({
            "metrics": extended_metrics,
            "trades": trades_data,
            "equity_curve": equity_sampled,
            "equity_timestamps": [str(d) for d in backtester.data.index[::step]] if len(equity) > 500 else [str(d) for d in backtester.data.index],
            "drawdown": [round(d, 2) for d in drawdown],
            "duration": _get_duration_str(backtester.data.index[0], backtester.data.index[-1]),
            "symbol": req.symbol if hasattr(req, 'symbol') and req.symbol else _backtest_state.get("loaded_data_info", {}).get("symbol", "Asset"),
            "strategy": req.strategy_name,
            "pnl_distribution": pnl_dist,
            "report": report,
            "initial_balance": req.initial_balance,
            "final_balance": round(backtester.balance, 2),
            "params_used": req.strategy_params or {},
            "timestamp": datetime.now().isoformat(),
        })
        _backtest_state["last_results"] = results
        
        _add_log(f"Backtest complete: {extended_metrics.get('total_trades', 0)} trades, "
                 f"PnL: ${extended_metrics.get('total_pnl', 0):.2f}, "
                 f"Win Rate: {extended_metrics.get('win_rate', 0):.1%}, "
                 f"Sharpe: {extended_metrics.get('sharpe_ratio', 0):.3f}")

        return results

    except Exception as e:
        _add_log(f"ERROR in backtest: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimize")
async def start_optimization(req: OptimizeRequest):
    """Start genetic parameter optimization (runs in background)."""
    df = _backtest_state.get("loaded_data")
    if df is None:
        raise HTTPException(status_code=400, detail="No data loaded. Load data first.")

    job = _backtest_state.get("optimizer_job") or {}
    if job.get("status") == "running":
        raise HTTPException(status_code=409, detail="Optimizer is already running")

    _add_log(f"Starting genetic optimization: pop={req.population_size}, gen={req.generations}")

    _backtest_state["optimizer_job"] = {
        "status": "running",
        "progress": 0,
        "total_generations": req.generations,
        "current_generation": 0,
        "best_fitness": 0,
        "best_params": {},
        "started_at": datetime.now().isoformat(),
    }

    def _run_optimizer():
        try:
            from src.engine.backtesting.backtester import Backtester
            from src.engine.core.genetic_optimizer import GeneticOptimizer
            import random
            from deap import tools
            
            # Map algorithm name
            from src.algorithms import list_algorithms
            algos = list_algorithms()
            algo_id = req.strategy_name
            for k, v in algos.items():
                if v['name'] == req.strategy_name:
                    algo_id = k
                    break

            # Setup logging redirection
            api_handler = ApiLogHandler()
            api_handler.setFormatter(logging.Formatter('%(name)s: %(message)s'))
            for l_name in ['GeneticOptimizer', 'Backtester']:
                l = logging.getLogger(l_name)
                l.addHandler(api_handler)
                l.propagate = False # Avoid double logging in console

            # Execution constraints for the adapter
            fixed_constraints = {
                'max_trades_per_day': req.max_trades_per_day,
                'start_hour': req.start_hour,
                'end_hour': req.end_hour,
                'ignore_filters': req.ignore_filters
            }

            # Bind the algo_id and fixed constraints correctly
            class BoundAdapter(PlatformStrategyAdapter):
                def __init__(self, params):
                    if params is None: 
                        params = {}
                    # Merge fixed constraints
                    full_params = {**params, **fixed_constraints}
                    full_params['_algo_name'] = algo_id
                    super().__init__({'algo_instance': None, 'params': full_params})

            backtester = Backtester(
                df, 
                initial_balance=req.initial_balance, 
                strategy_class=BoundAdapter,
                tick_size=req.tick_size,
                tick_value=req.tick_value
            )
            optimizer = GeneticOptimizer(backtester)

            # --- Custom Optimization Loop for Professional Logging ---
            pop_size = req.population_size
            ngen = req.generations
            
            _add_log(f"[SYSTEM] Initializing Genetic Population (n={pop_size})...")
            population = optimizer.toolbox.population(n=pop_size)
            
            # Initial evaluation
            fitnesses = list(map(optimizer.toolbox.evaluate, population))
            for ind, fit in zip(population, fitnesses):
                ind.fitness.values = fit

            global_best_ind = None
            
            for gen in range(1, ngen + 1):
                # Selection
                offspring = optimizer.toolbox.select(population, len(population))
                
                # Clone for safety
                offspring = list(map(optimizer.toolbox.clone, offspring))

                # Mate and Mutate
                for child1, child2 in zip(offspring[::2], offspring[1::2]):
                    if random.random() < req.crossover_rate:
                        optimizer.toolbox.mate(child1, child2)
                        del child1.fitness.values
                        del child2.fitness.values

                for mutant in offspring:
                    if random.random() < req.mutation_rate:
                        optimizer.toolbox.mutate(mutant)
                        del mutant.fitness.values

                # Evaluate new 
                invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
                fitnesses = map(optimizer.toolbox.evaluate, invalid_ind)
                for ind, fit in zip(invalid_ind, fitnesses):
                    ind.fitness.values = fit

                # Replace population
                population[:] = offspring
                
                # Update progress
                current_best_ind = tools.selBest(population, 1)[0]
                current_best_fit = current_best_ind.fitness.values[0]
                
                if global_best_ind is None or current_best_fit > global_best_ind.fitness.values[0]:
                    global_best_ind = optimizer.toolbox.clone(current_best_ind)

                _backtest_state["optimizer_job"].update({
                    "current_generation": gen,
                    "progress": int((gen / ngen) * 100),
                    "best_fitness": round(global_best_ind.fitness.values[0], 4),
                    "best_params": optimizer.individual_to_params(global_best_ind)
                })

                # --- PROFESSIONAL LOGGING ---
                # Retrieve stats via a quick backtest of the best to be neat
                best_results = backtester.run(optimizer.individual_to_params(global_best_ind))
                _add_log("="*60)
                _add_log(f" GENERATION {gen}/{ngen} COMPLETED ".center(60, "-"))
                _add_log(f"  > Global Best Fitness: {global_best_ind.fitness.values[0]:7.4f}")
                _add_log(f"  > Total PnL:         ${best_results.get('total_pnl', 0):9.2f}")
                _add_log(f"  > Win Rate:          {best_results.get('win_rate', 0)*100:6.1f}%")
                _add_log(f"  > Trades:            {best_results.get('total_trades', 0):6d}")
                _add_log("-" * 60)

            # Finish
            result = {
                "best_params": optimizer.individual_to_params(global_best_ind),
                "best_fitness": global_best_ind.fitness.values[0]
            }

            _backtest_state["optimizer_job"] = {
                "status": "completed",
                "progress": 100,
                "total_generations": req.generations,
                "current_generation": req.generations,
                "best_fitness": round(result["best_fitness"], 4),
                "best_params": {k: round(v, 4) if isinstance(v, float) else v for k, v in result["best_params"].items()},
                "completed_at": datetime.now().isoformat(),
            }

            # Save results
            results_dir = os.path.join(_ENGINE_DIR, "results")
            os.makedirs(results_dir, exist_ok=True)
            with open(os.path.join(results_dir, "best_params.json"), "w") as f:
                import json
                json.dump({
                    "best_params": result["best_params"],
                    "best_fitness": result["best_fitness"],
                }, f, indent=2, default=str)

            _add_log(f"Optimization complete! Best fitness: {result['best_fitness']:.4f}")

        except Exception as e:
            _backtest_state["optimizer_job"] = {
                "status": "error",
                "error": str(e),
                "progress": 0,
            }
            _add_log(f"Optimization ERROR: {e}")
            logger.error(traceback.format_exc())

    import threading
    thread = threading.Thread(target=_run_optimizer, daemon=True)
    thread.start()

    return {"status": "started", "message": f"Genetic optimizer started with pop={req.population_size}, gen={req.generations}"}


@router.get("/optimize/status")
async def get_optimization_status():
    """Check optimizer progress."""
    job = _backtest_state.get("optimizer_job")
    if job is None:
        return {"status": "idle"}
    return job


@router.post("/optimize/stop")
async def stop_optimization():
    """Cancel the current optimization job."""
    job = _backtest_state.get("optimizer_job")
    if job and job.get("status") == "running":
        _backtest_state["optimizer_job"]["status"] = "cancelled"
        _add_log("Optimization cancelled by user.")
        return {"status": "cancelled", "message": "Optimizer stopped."}
    return {"status": "idle", "message": "No running operation to stop."}


@router.get("/results")
@router.get("/results/latest")
async def get_latest_results():
    if not _backtest_state.get("last_results"):
        return {"backtest_results": None}
    return {"backtest_results": _backtest_state["last_results"]}

@router.get("/export/pdf")
async def export_pdf_report():
    """Generates a professional PDF report from the last backtest results."""
    results = _backtest_state.get("last_results")
    if not results:
        raise HTTPException(status_code=400, detail="No results found. Run a backtest first.")

    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        elements = []
        styles = getSampleStyleSheet()
        
        # Professional Styles
        title_style = ParagraphStyle(
            'TitleStyle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor("#f59e0b"),
            alignment=1, spaceAfter=20, fontName="Helvetica-Bold"
        )
        subtitle_style = ParagraphStyle(
            'SubtitleStyle', parent=styles['Normal'], fontSize=10, textColor=colors.gray,
            alignment=1, spaceAfter=30, fontName="Helvetica"
        )
        header_style = ParagraphStyle(
            'HeaderStyle', parent=styles['Heading2'], fontSize=12, textColor=colors.darkblue,
            spaceBefore=15, spaceAfter=10, fontName="Helvetica-Bold"
        )

        # 1. Logo and Header
        logo_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "images", "QuantumLLama.png")
        if os.path.exists(logo_path):
            img = Image(logo_path, 1.2*inch, 1.2*inch)
            img.hAlign = 'CENTER'
            elements.append(img)
            elements.append(Spacer(1, 10))

        elements.append(Paragraph("QUANTUM LLAMA TERMINAL", title_style))
        elements.append(Paragraph(f"BACKTEST ANALYSIS REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M')}", subtitle_style))
        
        # 2. Strategy Info
        info_data = [
            [Paragraph("<b>Strategy:</b>", styles['Normal']), results.get('strategy', 'Unknown')],
            [Paragraph("<b>Symbol:</b>", styles['Normal']), results.get('symbol', 'Unknown')],
            [Paragraph("<b>Duration:</b>", styles['Normal']), results.get('duration', 'Unknown')]
        ]
        info_table = Table(info_data, colWidths=[1.5*inch, 4*inch])
        info_table.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'LEFT'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
        elements.append(info_table)
        elements.append(Spacer(1, 20))

        # 3. Key Metrics Table
        metrics = results.get("metrics", {})
        m_data = [
            ["Metric", "Value", "Metric", "Value"],
            ["Total Net Profit", f"${metrics.get('total_pnl', 0):.2f}", "Profit Factor", f"{metrics.get('profit_factor', 0):.2f}"],
            ["Win Rate", f"{metrics.get('win_rate', 0)*100:.1f}%", "Max Drawdown", f"{metrics.get('max_drawdown', 0)*100:.2f}%"],
            ["Total Trades", metrics.get('total_trades', 0), "Sharpe Ratio", f"{metrics.get('sharpe_ratio', 0):.2f}"],
            ["Avg Win", f"${metrics.get('avg_win', 0):.2f}", "Avg Loss", f"${metrics.get('avg_loss', 0):.2f}"]
        ]
        met_table = Table(m_data, colWidths=[1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch])
        met_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f59e0b")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 10),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('BACKGROUND', (0,1), (-1,-1), colors.whitesmoke),
            ('GRID', (0,0), (-1,-1), 1, colors.white)
        ]))
        elements.append(Paragraph("Performance Summary", header_style))
        elements.append(met_table)
        elements.append(Spacer(1, 25))

        # 4. Equity Curve Chart
        elements.append(Paragraph("Equity Growth visualization", header_style))
        equity_data = results.get("equity_curve", [])
        if equity_data:
            plt.figure(figsize=(10, 4), dpi=100)
            plt.style.use('dark_background')
            plt.plot(equity_data, color='#f59e0b', linewidth=2)
            plt.fill_between(range(len(equity_data)), equity_data, min(equity_data), alpha=0.1, color='#f59e0b')
            plt.title("Equity Curve ($)", color='white', pad=10)
            plt.grid(True, alpha=0.1)
            
            chart_buffer = io.BytesIO()
            plt.savefig(chart_buffer, format='png', bbox_inches='tight', transparent=True)
            plt.close()
            chart_buffer.seek(0)
            
            chart_img = Image(chart_buffer, 6.5*inch, 2.5*inch)
            chart_img.hAlign = 'CENTER'
            elements.append(chart_img)
        
        elements.append(Spacer(1, 20))
        elements.append(PageBreak())

        # 5. Trades Table
        elements.append(Paragraph("Detailed Trade List (Partial)", header_style))
        trades = results.get("trades", [])
        t_header = ["#", "Type", "Entry", "Exit", "PnL ($)", "Duration"]
        t_rows = [t_header]
        
        for i, t in enumerate(trades[:100]): # Limit to first 100 on PDF
            t_rows.append([
                i+1,
                t.get('type', 'N/A'),
                f"{t.get('entry_price', 0):.2f}",
                f"{t.get('exit_price', 0):.2f}",
                f"{t.get('pnl', 0):.2f}",
                t.get('duration', '--')
            ])

        trade_table = Table(t_rows, colWidths=[0.5*inch, 1*inch, 1*inch, 1*inch, 1.2*inch, 1.8*inch])
        trade_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1e293b")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.whitesmoke])
        ]))
        elements.append(trade_table)
        
        if len(trades) > 100:
            elements.append(Paragraph(f"... and {len(trades)-100} more trades (view full list in terminal dashboard).", styles['Italic']))

        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        
        filename = f"Report_{results.get('symbol', 'Asset')}.pdf"
        return StreamingResponse(
            buffer, 
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        logger.error(f"Error generating PDF: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


@router.get("/logs")
async def get_logs(last: int = Query(50, description="Number of log lines to return")):
    """Get backtesting terminal log lines."""
    return _backtest_state["logs"][-last:]


@router.get("/data/info")
async def get_data_info():
    """Get info about currently loaded data."""
    info = _backtest_state.get("loaded_data_info")
    if info is None:
        return {"loaded": False}
    return {"loaded": True, **info}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _param_descriptions() -> Dict[str, str]:
    return {
        "delta_threshold": "Minimum |delta| to trigger a signal (higher = fewer signals)",
        "lookback_period": "Number of bars to look back for pattern detection",
        "imbalance_threshold": "Bid/Ask imbalance ratio threshold (0.0-1.0)",
        "stop_loss_ticks": "Stop-loss distance in ticks",
        "take_profit_ticks": "Take-profit distance in ticks",
        "rr_ratio": "Risk/Reward ratio for exit calculation",
        "min_volume": "Minimum volume filter for entries",
        "atr_multiplier": "ATR multiplier for dynamic SL/TP",
    }
