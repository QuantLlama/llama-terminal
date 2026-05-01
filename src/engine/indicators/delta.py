import pandas as pd
import numpy as np
from typing import Dict, Tuple


def calculate_delta(tick_data: pd.DataFrame) -> pd.Series:
    """Calcula Delta (compras agresivas - ventas agresivas)."""
    if 'volume' not in tick_data.columns:
        raise ValueError("Datos deben contener columna 'volume'")
    
    direction = tick_data.get('direction', None)
    if direction is not None:
        return direction * tick_data['volume']
    
    price_change = tick_data['last'].diff()
    volume = tick_data['volume']
    delta = np.where(price_change > 0, volume, np.where(price_change < 0, -volume, 0))
    
    return pd.Series(delta, index=tick_data.index)


def cumulative_delta(tick_data: pd.DataFrame) -> pd.Series:
    """Calcula Delta Acumulado (CVD)."""
    delta = calculate_delta(tick_data)
    return delta.cumsum()


def delta_divergence(price: pd.Series, delta: pd.Series, window: int = 10) -> pd.Series:
    """Detecta divergencia entre precio y delta."""
    price_trend = price.diff(window)
    delta_trend = delta.diff(window)
    
    divergence = np.where(
        (price_trend > 0) & (delta_trend < 0), -1,
        np.where((price_trend < 0) & (delta_trend > 0), 1, 0)
    )
    
    return pd.Series(divergence, index=price.index)


def aggressive_buying_pressure(tick_data: pd.DataFrame, window: int = 20) -> pd.Series:
    """Calcula presión de compra agresiva en ventana."""
    delta = calculate_delta(tick_data)
    aggressive_buying = delta[delta > 0].rolling(window).sum()
    
    result = pd.Series(0, index=tick_data.index)
    result.loc[aggressive_buying.index] = aggressive_buying
    
    return result


def aggressive_selling_pressure(tick_data: pd.DataFrame, window: int = 20) -> pd.Series:
    """Calcula presión de venta agresiva en ventana."""
    delta = calculate_delta(tick_data)
    aggressive_selling = delta[delta < 0].rolling(window).sum()
    
    result = pd.Series(0, index=tick_data.index)
    result.loc[aggressive_selling.index] = aggressive_selling
    
    return result


def delta_momentum(delta: pd.Series, window: int = 5) -> pd.Series:
    """Calcula momentum del delta."""
    return delta.rolling(window).mean()
