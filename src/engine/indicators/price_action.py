import pandas as pd
import numpy as np
from typing import Dict, List, Tuple


def detect_key_levels(high: pd.Series, low: pd.Series, window: int = 20) -> Dict[str, pd.Series]:
    """Detecta niveles clave (máximos, mínimos, soportes, resistencias)."""
    rolling_max = high.rolling(window).max()
    rolling_min = low.rolling(window).min()
    
    resistance = high.where(high >= rolling_max.shift(1))
    support = low.where(low <= rolling_min.shift(1))
    
    return {
        'resistance': resistance,
        'support': support
    }


def detect_rejection_candles(open: pd.Series, high: pd.Series, 
                             low: pd.Series, close: pd.Series) -> pd.Series:
    """Detecta velas de rechazo (pin bars)."""
    body = abs(close - open)
    total_range = high - low
    
    upper_wick = high - np.maximum(open, close)
    lower_wick = np.minimum(open, close) - low
    
    rejection = pd.Series(0, index=open.index)
    
    rejection_mask = (upper_wick / total_range > 0.6) & (body / total_range < 0.3)
    rejection[rejection_mask] = -1  # Bearish rejection
    
    rejection_mask = (lower_wick / total_range > 0.6) & (body / total_range < 0.3)
    rejection[rejection_mask] = 1   # Bullish rejection
    
    return rejection


def detect_engulfing(open: pd.Series, high: pd.Series, 
                     low: pd.Series, close: pd.Series) -> pd.Series:
    """Detecta patrones engulfing."""
    prev_open = open.shift(1)
    prev_close = close.shift(1)
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    
    bullish_engulfing = (
        (prev_close < prev_open) &  # Previous red candle
        (close > open) &           # Current green candle
        (open <= prev_close) &      # Current opens below prev close
        (close >= prev_open)        # Current closes above prev open
    )
    
    bearish_engulfing = (
        (prev_close > prev_open) &  # Previous green candle
        (close < open) &            # Current red candle
        (open >= prev_close) &      # Current opens above prev close
        (close <= prev_open)        # Current closes below prev open
    )
    
    engulfing = pd.Series(0, index=open.index)
    engulfing[bullish_engulfing] = 1
    engulfing[bearish_engulfing] = -1
    
    return engulfing


def market_structure(high: pd.Series, low: pd.Series) -> pd.Series:
    """Analiza estructura del mercado (higher highs/lows, lower highs/lows)."""
    hh = high.where(high > high.rolling(5).max().shift(1))
    hl = low.where(low > low.rolling(5).max().shift(1))
    ll = low.where(low < low.rolling(5).min().shift(1))
    lh = high.where(high < high.rolling(5).min().shift(1))
    
    structure = pd.Series(0, index=high.index)
    
    structure[~hh.isna() & ~hl.isna()] = 1    # Bullish structure
    structure[~ll.isna() & ~lh.isna()] = -1   # Bearish structure
    
    return structure


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, 
         volume: pd.Series) -> pd.Series:
    """Calcula VWAP."""
    typical_price = (high + low + close) / 3
    vwap_values = (typical_price * volume).cumsum() / volume.cumsum()
    
    return vwap_values
