import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any

try:
    import vectorbt as vbt
    VBT_AVAILABLE = True
except ImportError:
    VBT_AVAILABLE = False

class StrategyLive:
    """
     ESTRATEGIA EN VIVO (VectorBT)
    plataforma Quantum Llama.
    """
    def __init__(self, 
                 close_name='Close', 
                 open_name='Open', 
                 high_name='High', 
                 low_name='Low', 
                 volume_name='Volume',
                 window_long=20,
                 window_short=5,
                 window_absorption=10,
                 threshold_volume_absorption=1.5,
                 threshold_rsi_overbought=70,
                 threshold_rsi_oversold=30,
                 stop_loss=0.02,
                 take_profit=0.04):

        self.close_name = close_name
        self.open_name = open_name
        self.high_name = high_name
        self.low_name = low_name
        self.volume_name = volume_name
        self.window_long = window_long
        self.window_short = window_short
        self.window_absorption = window_absorption
        self.threshold_volume_absorption = threshold_volume_absorption
        self.threshold_rsi_overbought = threshold_rsi_overbought
        self.threshold_rsi_oversold = threshold_rsi_oversold
        self.stop_loss = stop_loss
        self.take_profit = take_profit

    def update(self, data: pd.DataFrame):
        """
        Lógica de ejecución en tiempo real.
        Returns: (signal: str, metadata: dict)
        """
        if len(data) < self.window_long + 1:
            return "HOLD", {"message": "Datos insuficientes"}

        close_prices = data[self.close_name]
        open_prices = data[self.open_name]
        volumes = data[self.volume_name]

        # Calcular indicadores (último valor) — pure pandas, no vectorbt dependency
        ema_long = close_prices.ewm(span=self.window_long, adjust=False).mean().iloc[-1]
        ema_short = close_prices.ewm(span=self.window_short, adjust=False).mean().iloc[-1]
        # RSI calculation
        delta = close_prices.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rsi = (100 - (100 / (1 + gain / (loss + 1e-10)))).iloc[-1]

        # Calcular absorción (última ventana)
        window = data.iloc[-self.window_absorption:]
        absorption = self._calculate_absorption_single(window)

        # Máximos/Mínimos históricos recientes
        recent_high = data[self.high_name].iloc[:-1].max()
        recent_low = data[self.low_name].iloc[:-1].min()
        current_close = close_prices.iloc[-1]

        # Lógica de señales
        if (ema_short > ema_long and rsi < self.threshold_rsi_oversold and 
            absorption > 0 and current_close > recent_high):
            return "BUY", {"message": "Cruce EMA + RSI + Absorción + Ruptura"}
        
        if (ema_short < ema_long and rsi > self.threshold_rsi_overbought and 
            absorption < 0 and current_close < recent_low):
            return "SELL", {"message": "Cruce EMA + RSI + Absorción + Ruptura"}

        return "HOLD", {"message": "Sin señal clara"}

    def _calculate_absorption_single(self, window_df):
        up_candles = window_df[self.close_name] > window_df[self.open_name]
        down_candles = window_df[self.close_name] < window_df[self.open_name]
        
        vol_up = window_df[up_candles][self.volume_name].mean() if up_candles.any() else 0
        vol_down = window_df[down_candles][self.volume_name].mean() if down_candles.any() else 0
        
        if vol_up > vol_down * self.threshold_volume_absorption: return 1.0
        if vol_down > vol_up * self.threshold_volume_absorption: return -1.0
        return 0.0

    def run_backtest(self, data):
        """
        Mantenemos la capacidad de backtest original de VectorBT.
        """
        if not VBT_AVAILABLE:
            raise ImportError("vectorbt is required for backtesting. Install with: pip install vectorbt")
        close_prices = data[self.close_name]
        ema_long = close_prices.ewm(span=self.window_long, adjust=False).mean()
        ema_short = close_prices.ewm(span=self.window_short, adjust=False).mean()
        
        # Detect crossovers using pandas shift
        entries = (ema_short > ema_long) & (ema_short.shift(1) <= ema_long.shift(1))
        exits = (ema_short < ema_long) & (ema_short.shift(1) >= ema_long.shift(1))
        
        pf = vbt.Portfolio.from_signals(close_prices, entries, exits, freq='1D')
        return pf


if __name__ == '__main__':
    import sys
    import os
    
    # -------------------------------------------------------------------------
    # FIX: Force UTF-8 encoding for Windows Console to prevent Emoji crashes
    # -------------------------------------------------------------------------
    if sys.platform == "win32":
        import codecs
        try:
            sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
            sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())
        except Exception as e:
            print(f"Warning: Could not force UTF-8 (Error: {e})")

    # Calculate project root for imports
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "../../"))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        from src.live.live_trade import run_live_trading
        
        # Default configuration for testing
        print(" Starting StrategyLive (Direct Execution)...")
        run_live_trading(
            sys_ticker="MNQ=F", 
            asset_type="Futures", 
            platform="mt5", 
            timeframe="1m", 
            algo_name="StrategyLive", # Uses this file/class name
            algo_config={}
        )
    except ImportError as e:
        print(f" Error importing live trading engine: {e}")
        print(f"Project Root: {project_root}")
    except Exception as e:
        print(f" Runtime Error: {e}")
        import traceback
        traceback.print_exc()
