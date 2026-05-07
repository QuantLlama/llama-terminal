import pandas as pd
import numpy as np
from typing import Dict, List, Tuple


def volume_profile(price: pd.Series, volume: pd.Series, bins: int = 50) -> pd.DataFrame:
    """Calcula Volume Profile."""
    price_bins = pd.cut(price, bins=bins)
    vol_profile = volume.groupby(price_bins).sum().sort_values(ascending=False)
    
    total_volume = vol_profile.sum()
    vol_profile_pct = (vol_profile / total_volume) * 100
    
    return pd.DataFrame({
        'volume': vol_profile,
        'volume_pct': vol_profile_pct
    })


def vah_val(volume_profile: pd.DataFrame) -> Tuple[float, float]:
    """Calcula VAH (Volume Area High) y VAL (Volume Area Low)."""
    vol_profile = volume_profile['volume']
    total_vol = vol_profile.sum()
    
    target_vol = total_vol * 0.7
    cumulative = 0
    
    vah = None
    val = None
    
    for idx in vol_profile.index:
        cumulative += vol_profile[idx]
        if vah is None:
            vah = idx.mid
        if cumulative >= target_vol:
            val = idx.mid
            break
    
    return vah, val


def poc(volume_profile: pd.DataFrame) -> float:
    """Calcula POC (Point of Control)."""
    return volume_profile['volume'].idxmax().mid


def tpo_profile(bars: pd.DataFrame) -> pd.DataFrame:
    """Calcula Time Price Opportunity profile."""
    prices = []
    
    for _, bar in bars.iterrows():
        price_range = np.arange(bar['low'], bar['high'] + 0.25, 0.25)
        prices.extend(price_range)
    
    price_counts = pd.Series(prices).value_counts()
    return price_counts.to_frame('count')


def volume_at_price(price: pd.Series, volume: pd.Series, target_price: float, tolerance: float = 0.25) -> float:
    """Calcula volumen total en nivel de precio específico."""
    mask = (price >= target_price - tolerance) & (price <= target_price + tolerance)
    return volume[mask].sum()
