"""
CazaStop PRO Indicator - PROFESSIONAL VISUALIZATION VERSION
Solves rectangle overflow, label pollution, and opacity issues
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from functools import lru_cache
import logging

# Disable all prints in production
logging.getLogger(__name__).setLevel(logging.CRITICAL)


class Zone:
    """Optimized zone representation with memory efficiency."""
    __slots__ = ['nivel', 'is_long', 'inicio_time', 'vida', 'vol_ratio', 'activa']
    
    def __init__(self, nivel: float, is_long: bool, inicio_time: int, vol_ratio: float = 1.0):
        self.nivel = nivel
        self.is_long = is_long
        self.inicio_time = inicio_time
        self.vida = 0
        self.vol_ratio = vol_ratio
        self.activa = True


class CazaStopIndicator:
    """
    CazaStop PRO - Professional visualization for real-money trading
    Clean, transparent overlays that don't interfere with chart analysis
    """
    
    def __init__(self, config: Optional[Dict] = None):
        config = config or {}
        
        # Parameters matching NinjaTrader defaults
        self.swing_bars = config.get('swing_bars', 5) # Increased for precision
        self.lookback = config.get('lookback', 10)
        self.dist_ticks = config.get('dist_ticks', 60)
        self.buffer_ticks = config.get('buffer_ticks', 10)
        self.vida_max = config.get('vida_max', 30)
        
        # TP Volume settings
        self.lookback_tp = config.get('lookback_tp', 100)
        self.ticks_tp = config.get('ticks_tp', 6)
        self.mostrar_tp = config.get('mostrar_tp', True)
        
        # Analysis flags
        self.analisis_vol = config.get('analisis_vol', True)
        self.dibujar_safe = config.get('dibujar_safe', True)
        
        # Performance optimization: Cache computed values
        self._cached_tick_size: Optional[float] = None
        self._last_df_hash: Optional[int] = None
        self._existing_zones: List[Zone] = []
        self._last_processed_bar: int = -1
        
    def get_config(self) -> Dict:
        return {
            'swing_bars': self.swing_bars,
            'lookback': self.lookback,
            'dist_ticks': self.dist_ticks,
            'buffer_ticks': self.buffer_ticks,
            'vida_max': self.vida_max,
            'lookback_tp': self.lookback_tp,
            'ticks_tp': self.ticks_tp,
            'mostrar_tp': self.mostrar_tp,
            'analisis_vol': self.analisis_vol,
            'dibujar_safe': self.dibujar_safe
        }
    
    @lru_cache(maxsize=1)
    def _get_fast_tick_size(self, df_hash: int, close_values: Tuple[float, ...]) -> float:
        """Ultra-fast cached tick size calculation."""
        if len(close_values) < 2:
            return 0.25
        
        # Use numpy for vectorized calculation - MUCH faster
        price_diffs = np.abs(np.diff(close_values))
        non_zero_diffs = price_diffs[price_diffs > 0]
        
        if len(non_zero_diffs) == 0:
            return 0.25
            
        return float(np.min(non_zero_diffs))
    
    def _fast_swing_check(self, highs: np.ndarray, lows: np.ndarray, idx: int) -> Tuple[bool, bool]:
        """Vectorized swing high/low detection."""
        if idx < self.swing_bars:
            return False, False
        
        # Vectorized comparison - MUCH faster than loops
        lookback_slice = slice(idx - self.swing_bars, idx)
        
        # Swing low check
        current_low = lows[idx]
        is_swing_low = np.all(lows[lookback_slice] > current_low)
        
        # Swing high check  
        current_high = highs[idx]
        is_swing_high = np.all(highs[lookback_slice] < current_high)
        
        return is_swing_low, is_swing_high
    
    def _fast_volume_ratio(self, volumes: np.ndarray, idx: int) -> float:
        """Vectorized volume ratio calculation."""
        if idx < self.lookback:
            return 1.0
            
        lookback_slice = slice(idx - self.lookback, idx)
        avg_vol = np.mean(volumes[lookback_slice])
        
        if avg_vol <= 0:
            return 1.0
            
        return float(volumes[idx] / avg_vol)
    
    def _convert_timestamp_fast(self, ts) -> int:
        """Optimized timestamp conversion."""
        if isinstance(ts, (int, np.integer)):
            return int(ts)
        elif hasattr(ts, 'timestamp'):
            return int(ts.timestamp())
        elif isinstance(ts, np.datetime64):
            return int(pd.Timestamp(ts).timestamp())
        else:
            return int(float(ts))
    
    def _update_zones_lifecycle(self, zones: List[Zone], current_price: float, tick_size: float) -> List[Zone]:
        """Optimized zone lifecycle management."""
        active_zones = []
        dist = self.dist_ticks * tick_size
        
        for zone in zones:
            zone.vida += 1
            
            # Quick elimination checks
            if zone.vida > self.vida_max:
                continue
                
            # Price distance check
            if zone.is_long and current_price < zone.nivel - dist:
                continue
            if not zone.is_long and current_price > zone.nivel + dist:
                continue
                
            zone.activa = True
            active_zones.append(zone)
            
        return active_zones
    
    def _calculate_tp_zone_fast(self, df: pd.DataFrame, tick_size: float) -> Optional[Dict]:
        """Optimized TP zone calculation using numpy."""
        if not self.mostrar_tp or len(df) < self.lookback_tp:
            return None
            
        # Use numpy arrays for speed
        recent_data = df.iloc[-self.lookback_tp:]
        closes = recent_data['Close'].values
        volumes = recent_data['Volume'].values
        
        # Vectorized price bucketing
        price_ticks = np.round(closes / tick_size) * tick_size
        
        # Create volume profile efficiently
        unique_prices, inverse_indices = np.unique(price_ticks, return_inverse=True)
        volume_profile = np.bincount(inverse_indices, weights=volumes)
        
        if len(volume_profile) == 0:
            return None
            
        # Find POC (Point of Control) - price with max volume
        poc_idx = np.argmax(volume_profile)
        poc = float(unique_prices[poc_idx])
        poc_vol = float(volume_profile[poc_idx])
        
        return {
            'poc': poc,
            'level_top': poc + self.ticks_tp * tick_size,
            'level_bottom': poc - self.ticks_tp * tick_size,
            'volume': poc_vol,
            'color': 'rgba(59, 130, 246, 0.08)',  # ULTRA transparent
            'border_color': 'rgba(59, 130, 246, 0.3)'  # Faint border
        }
    
    def calculate(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Ultra-fast CazaStop calculation with PROFESSIONAL VISUALIZATION
        """
        if len(df) < max(self.swing_bars, self.lookback) + 2:
            return {'zones': [], 'tp_zone': None, 'metadata': {'active_zones': 0}}
        
        # Convert to numpy arrays ONCE for maximum speed
        highs = df['High'].values
        lows = df['Low'].values
        closes = df['Close'].values
        volumes = df['Volume'].values
        
        # Fast tick size with caching
        df_hash = hash(tuple(closes[:10]))  # Simple hash for caching
        if self._cached_tick_size is None or self._last_df_hash != df_hash:
            self._cached_tick_size = self._get_fast_tick_size(df_hash, tuple(closes))
            self._last_df_hash = df_hash
        
        tick_size = self._cached_tick_size
        current_bar_idx = len(df) - 1
        
        # FIX: Get actual timestamp for current_time
        if 'timestamp' in df.columns:
            current_time = self._convert_timestamp_fast(df.iloc[-1]['timestamp'])
        elif 'time' in df.columns:
            current_time = self._convert_timestamp_fast(df.iloc[-1]['time'])
        else:
            current_time = self._convert_timestamp_fast(df.index[-1])
        
        new_zones = []
        
        # FIX: Process more bars if starting fresh (stateless mode)
        if self._last_processed_bar == -1:
            # First run: check up to 500 previous bars for existing swings
            start_check = max(self.swing_bars, current_bar_idx - 500)
        else:
            # Subsequent runs: only check last 5 bars
            start_check = max(self.swing_bars, current_bar_idx - 5)
        
        for i in range(start_check, current_bar_idx + 1):
            if i <= self._last_processed_bar:
                continue  # Skip already processed bars
                
            is_swing_low, is_swing_high = self._fast_swing_check(highs, lows, i)
            
            # Get timestamp efficiently
            if 'timestamp' in df.columns:
                ts = self._convert_timestamp_fast(df.iloc[i]['timestamp'])
            elif 'time' in df.columns:
                ts = self._convert_timestamp_fast(df.iloc[i]['time'])
            else:
                ts = self._convert_timestamp_fast(df.index[i])
            
            # Create zones for new swing points
            if is_swing_low:
                vol_ratio = self._fast_volume_ratio(volumes, i) if self.analisis_vol else 1.0
                new_zones.append(Zone(
                    nivel=float(lows[i]),
                    is_long=True,
                    inicio_time=ts,
                    vol_ratio=vol_ratio
                ))
                
            if is_swing_high:
                vol_ratio = self._fast_volume_ratio(volumes, i) if self.analisis_vol else 1.0
                new_zones.append(Zone(
                    nivel=float(highs[i]),
                    is_long=False,
                    inicio_time=ts,
                    vol_ratio=vol_ratio
                ))
        
        # Add new zones to existing ones - HIGHER PRECISION FILTERING
        for zone in new_zones:
            # Only add zones with significant volume ratio or first few zones
            if zone.vol_ratio >= 1.2 or len(self._existing_zones) < 5:
                self._existing_zones.append(zone)
                
        self._last_processed_bar = current_bar_idx
        
        # Update lifecycle for ALL zones
        current_price = float(closes[-1])
        active_zones = self._update_zones_lifecycle(self._existing_zones, current_price, tick_size)
        
        # Limit zone count to prevent memory bloat
        if len(self._existing_zones) > 100:
            self._existing_zones = self._existing_zones[-50:]  # Keep last 50 zones
        
        # PROFESSIONAL ZONE OUTPUT - Clean and transparent
        zones_output = []
        dist = self.dist_ticks * tick_size
        buffer = self.buffer_ticks * tick_size
        
        for zone in active_zones:
            # Calculate zone lifespan for visualization (shorter = more faded)
            age_factor = min(1.0, zone.vida / self.vida_max)
            opacity_factor = 0.06 + (age_factor * 0.04)  # 0.06 to 0.1 (ultra transparent)
            
            if zone.is_long:
                # LONG zone: danger ABOVE swing low
                zones_output.append({
                    'start_time': zone.inicio_time,
                    'end_time': current_time,  # FIX: No infinite rectangles!
                    'level_top': zone.nivel,
                    'level_bottom': zone.nivel - dist,
                    'type': 'danger',
                    'direction': 'long',
                    # ULTRA transparent colors - spectral effect
                    'color': f'rgba(239, 68, 68, {opacity_factor})',  # Ultra faint red
                    'border_color': f'rgba(239, 68, 68, {opacity_factor * 2})',
                    # NO labels for danger zones - visual pollution
                    'show_label': False
                })
                
                # Safe zone below danger zone - even more subtle
                if self.dibujar_safe:
                    zones_output.append({
                        'start_time': zone.inicio_time,
                        'end_time': current_time,
                        'level_top': zone.nivel - dist,
                        'level_bottom': zone.nivel - dist - buffer,
                        'type': 'safe',
                        'direction': 'long',
                        'color': f'rgba(34, 197, 94, {opacity_factor * 0.8})',  # Even more faint
                        'border_color': f'rgba(34, 197, 94, {opacity_factor * 1.5})',
                        # ONLY safe zones get minimal labels
                        'show_label': zone.vida <= 5  # Only show for very new zones
                    })
            else:
                # SHORT zone: danger BELOW swing high
                zones_output.append({
                    'start_time': zone.inicio_time,
                    'end_time': current_time,  # FIX: No infinite rectangles!
                    'level_top': zone.nivel + dist,
                    'level_bottom': zone.nivel,
                    'type': 'danger',
                    'direction': 'short',
                    'color': f'rgba(239, 68, 68, {opacity_factor})',  # Ultra faint red
                    'border_color': f'rgba(239, 68, 68, {opacity_factor * 2})',
                    'show_label': False
                })
                
                # Safe zone above danger zone
                if self.dibujar_safe:
                    zones_output.append({
                        'start_time': zone.inicio_time,
                        'end_time': current_time,
                        'level_top': zone.nivel + dist + buffer,
                        'level_bottom': zone.nivel + dist,
                        'type': 'safe',
                        'direction': 'short',
                        'color': f'rgba(34, 197, 94, {opacity_factor * 0.8})',  # Ultra faint green
                        'border_color': f'rgba(34, 197, 94, {opacity_factor * 1.5})',
                        'show_label': zone.vida <= 5  # Only show for very new zones
                    })
        
        # Fast TP zone calculation - ULTRA subtle
        tp_zone = self._calculate_tp_zone_fast(df, tick_size)
        
        return {
            'zones': zones_output,
            'tp_zone': tp_zone,
            'metadata': {
                'active_zones': len(active_zones),
                'total_zones_output': len(zones_output),
                'tick_size': tick_size,
                'new_zones': len(new_zones),
                'performance_mode': 'optimized',
                'visualization_mode': 'professional'
            }
        }