import pandas as pd
import numpy as np
from typing import Dict, List, Tuple


def detect_imbalance(bid_volume: pd.Series, ask_volume: pd.Series, 
                    threshold: float = 0.7) -> pd.Series:
    """Detecta imbalance bid/ask."""
    total_vol = bid_volume + ask_volume
    bid_ratio = bid_volume / total_vol
    
    imbalance = np.where(
        bid_ratio >= threshold, 'BID_DOMINANCE',
        np.where(bid_ratio <= (1 - threshold), 'ASK_DOMINANCE', 'BALANCED')
    )
    
    return pd.Series(imbalance, index=bid_volume.index)


def absorption_detection(tick_data: pd.DataFrame, window: int = 20) -> pd.Series:
    """Detecta absorción (gran volumen agresivo sin movimiento de precio)."""
    delta = tick_data.get('delta', tick_data['last'].diff() * tick_data['volume'])
    price_change = tick_data['last'].diff().abs()
    
    absorption_signals = pd.Series(0, index=tick_data.index)
    
    for i in range(window, len(tick_data)):
        delta_window = delta.iloc[i-window:i]
        price_change_window = price_change.iloc[i-window:i]
        
        if abs(delta_window.sum()) > 0:
            efficiency = price_change_window.sum() / abs(delta_window.sum())
            
            if efficiency < 0.5 and abs(delta_window.sum()) > 100:
                absorption_signals.iloc[i] = 1
    
    return absorption_signals


def resting_orders_detection(bid: pd.Series, ask: pd.Series, volume: pd.Series, 
                            threshold: int = 500) -> pd.Series:
    """Detecta grandes órdenes en book."""
    signals = pd.Series(0, index=bid.index)
    
    for i in range(1, len(bid)):
        if volume[i] > threshold:
            if ask[i] > ask[i-1]:
                signals.iloc[i] = 1  # Ask wall
            elif bid[i] < bid[i-1]:
                signals.iloc[i] = -1  # Bid wall
    
    return signals


def order_book_depth(bid: pd.Series, ask: pd.Series, levels: int = 5) -> Dict[str, pd.DataFrame]:
    """Calcula profundidad del order book."""
    return {
        'bid_depth': bid.rolling(levels).sum(),
        'ask_depth': ask.rolling(levels).sum()
    }
