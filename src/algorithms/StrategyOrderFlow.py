import pandas as pd
import numpy as np
import os
import sys

# Import from the unified engine package
from src.engine.core.strategy_engine import StrategyEngine

class StrategyOrderFlow:
    """
    ESTRATEGIA ORDER FLOW (Engine)
    Uses the unified src/engine package for live execution.
    It evaluates Delta Divergence, Cumulative Delta, and VWAP.
    """
    def __init__(self, 
                 delta_threshold=100,
                 lookback_period=10,
                 imbalance_threshold=0.7,
                 stop_loss_ticks=8,
                 take_profit_ticks=12,
                 rr_ratio=1.5,
                 min_volume=1000,
                 atr_multiplier=1.5):
        
        self.params = {
            'delta_threshold': delta_threshold,
            'lookback_period': lookback_period,
            'imbalance_threshold': imbalance_threshold,
            'stop_loss_ticks': stop_loss_ticks,
            'take_profit_ticks': take_profit_ticks,
            'rr_ratio': rr_ratio,
            'min_volume': min_volume,
            'atr_multiplier': atr_multiplier
        }
        self.engine = StrategyEngine(self.params)
        
    def update(self, data: pd.DataFrame):
        """
        Lógica de ejecución en tiempo real.
        Returns: (signal: str, metadata: dict)
        """
        if len(data) < self.params['lookback_period'] + 1:
            return "HOLD", {"message": "Datos insuficientes"}
        
        # Prepare formatting for Algoritest engine
        df = data.copy()
        
        # Mapping generic OHLCV to Algoritest expected columns
        if 'Close' in df.columns:
            df['close'] = df['Close']
            df['last'] = df['Close']
        if 'Open' in df.columns:
            df['open'] = df['Open']
        if 'High' in df.columns:
            df['high'] = df['High']
        if 'Low' in df.columns:
            df['low'] = df['Low']
        if 'Volume' in df.columns:
            df['volume'] = df['Volume']
            df['real_volume'] = df['Volume']
            
        # Add direction for delta calculation
        if 'direction' not in df.columns and 'close' in df.columns and 'open' in df.columns:
            df['direction'] = np.where(df['close'] > df['open'], 1, np.where(df['close'] < df['open'], -1, 0))
            
        try:
            # Get signals from engine
            signals = self.engine.generate_signals(df)
            
            # Extract latest signal
            latest_signal = signals['signal'].iloc[-1]
            
            if latest_signal == 1:
                return "BUY", {"message": "Order Flow: Divergencia Alcista (Delta +)"}
            elif latest_signal == -1:
                return "SELL", {"message": "Order Flow: Divergencia Bajista (Delta -)"}
            
        except Exception as e:
            return "HOLD", {"message": f"Error evaluando señales: {str(e)}"}
            
        return "HOLD", {"message": "Sin señal clara"}

if __name__ == '__main__':
    print("Testing StrategyOrderFlow wrapper...")
