import pandas as pd
import numpy as np
from src.utils.indicators import get_adx, get_rsi, get_atr, get_ema

class MarketFilter:
    def __init__(self):
        pass

    def calculate_indicators(self, df):
        if len(df) < 30:
            return df
        
        df['ADX'] = get_adx(df['High'], df['Low'], df['Close'])
        df['RSI'] = get_rsi(df['Close'])
        df['ATR'] = get_atr(df['High'], df['Low'], df['Close'])
        df['EMA'] = get_ema(df['Close'], period=50)
        return df
    def check_conditions(self, df, signal, config):
        if df.empty or len(df) < 50: 
            return False, "Not enough data"
        last_row = df.iloc[-1]
        min_adx = config.get("min_adx", 20)
        if last_row['ADX'] < min_adx:
            return False, f"Low ADX ({last_row['ADX']:.2f} < {min_adx})"
        rsi_upper = config.get("rsi_upper", 70)
        rsi_lower = config.get("rsi_lower", 30)
        if signal == "BUY" and last_row['RSI'] > rsi_upper:
            return False, f"RSI Overbought ({last_row['RSI']:.2f} > {rsi_upper})"
        if signal == "SELL" and last_row['RSI'] < rsi_lower:
            return False, f"RSI Oversold ({last_row['RSI']:.2f} < {rsi_lower})"
        use_ema_filter = config.get("use_ema_filter", True)
        if use_ema_filter and 'EMA' in last_row:
            if signal == "BUY" and last_row['Close'] < last_row['EMA']:
                 return False, f"Counter Trend (Price {last_row['Close']:.2f} < EMA {last_row['EMA']:.2f})"
            if signal == "SELL" and last_row['Close'] > last_row['EMA']:
                 return False, f"Counter Trend (Price {last_row['Close']:.2f} > EMA {last_row['EMA']:.2f})"
        require_candle_confirmation = config.get("require_candle_confirmation", True)
        if require_candle_confirmation:
            is_green = last_row['Close'] > last_row['Open']
            is_red = last_row['Close'] < last_row['Open']
            if signal == "BUY" and not is_green:
                return False, "Candle Color Mismatch (Red Candle for BUY)"
            if signal == "SELL" and not is_red:
                return False, "Candle Color Mismatch (Green Candle for SELL)"
        return True, "OK"
    def get_dynamic_threshold(self, df, multiplier=1.0):
        if 'ATR' not in df.columns or df.empty:
            return 0.0001 
        last_atr = df['ATR'].iloc[-1]
        return last_atr * multiplier