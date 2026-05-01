import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

try:
    import talib
    HAS_TALIB = True
except (ImportError, OSError):
    HAS_TALIB = False
    talib = None

def get_rsi(prices, period=14):
    if HAS_TALIB:
        return talib.RSI(prices, timeperiod=period)
    
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_atr(high, low, close, period=14):
    if HAS_TALIB:
        return talib.ATR(high, low, close, timeperiod=period)
    
    tr = pd.concat([high - low, 
                    (high - close.shift()).abs(), 
                    (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def get_adx(high, low, close, period=14):
    if HAS_TALIB:
        return talib.ADX(high, low, close, timeperiod=period)
    
    # Simplified ADX fallback
    up_move = high.diff()
    down_move = low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (pd.Series(plus_dm, index=high.index).rolling(window=period).mean() / atr)
    minus_di = 100 * (pd.Series(minus_dm, index=high.index).rolling(window=period).mean() / atr)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.rolling(window=period).mean()

def get_ema(prices, period=20):
    if HAS_TALIB:
        return talib.EMA(prices, timeperiod=period)
    return prices.ewm(span=period, adjust=False).mean()
