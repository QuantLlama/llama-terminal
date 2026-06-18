import numpy as np
import pandas as pd
from typing import Dict, Any, List

class LiquidityHeatmapIndicator:
    """
    Liquidity Heatmap Indicator (Market Depth / Order Book Heatmap).
    
    This indicator approximates liquidity depth if full L2 data is unavailable, 
    by distributing volume across the candle range or aggregating actual L2 order book
    snapshots if passed in the dataframe.
    """

    def __init__(self, config: Dict = None):
        self.config = config or {}
        # Tick size or price grouping for the heatmap bins
        self.tick_size = float(self.config.get('tick_size', 0.25))
        # Sensitivity: filter out nodes with very low liquidity to reduce noise
        self.sensitivity_threshold = float(self.config.get('heatmap_sensitivity', 0.05))
        # Smoothing period for historical liquidity (decay factor)
        self.decay_factor = float(self.config.get('heatmap_decay', 0.95))

    def calculate(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate Heatmap clusters.
        If 'bid_depth' and 'ask_depth' columns (L2 data) exist, uses them.
        Otherwise, approximates using OHLCV volume distribution.
        """
        if df.empty or len(df) < 2:
            return {'data': []}

        df = df.copy()
        result_data = []
        
        # Determine time column
        if 'timestamp' in df.columns:
            times = df['timestamp'].values.astype(np.int64) // 10**9
        elif 'time' in df.columns:
            times = df['time'].values
        else:
            times = df.index.values

        # Track rolling liquidity across price levels (dictionary: price -> volume_score)
        liquidity_map = {}

        has_l2 = 'bid_depth' in df.columns and 'ask_depth' in df.columns

        # --- SAFEGUARD AGAINST HUGE DATA ---
        # If the average candle range is massive relative to tick_size, scale tick_size up
        # This prevents generating millions of bins for assets like BTC if tick_size=0.25
        avg_range = (df['High'] - df['Low']).mean()
        if avg_range > 0 and (avg_range / self.tick_size) > 80:
            self.tick_size = max(self.tick_size, avg_range / 80.0)

        for i in range(len(df)):
            row = df.iloc[i]
            current_time = int(times[i])
            
            # Apply decay to old liquidity to fade it out
            for p in list(liquidity_map.keys()):
                liquidity_map[p] *= self.decay_factor
                if liquidity_map[p] < self.sensitivity_threshold:
                    del liquidity_map[p]

            candle_heatmap = []

            if has_l2:
                # Assuming bid_depth/ask_depth are dicts or stringified JSON mapping price -> volume
                import json
                try:
                    bids = json.loads(row['bid_depth']) if isinstance(row['bid_depth'], str) else row['bid_depth']
                    asks = json.loads(row['ask_depth']) if isinstance(row['ask_depth'], str) else row['ask_depth']
                    
                    for price_str, vol in bids.items():
                        p = float(price_str)
                        bin_price = round(p / self.tick_size) * self.tick_size
                        liquidity_map[bin_price] = liquidity_map.get(bin_price, 0) + float(vol)
                        
                    for price_str, vol in asks.items():
                        p = float(price_str)
                        bin_price = round(p / self.tick_size) * self.tick_size
                        liquidity_map[bin_price] = liquidity_map.get(bin_price, 0) + float(vol)
                except Exception:
                    pass
            else:
                # Approximation based on OHLCV
                high, low, vol = row['High'], row['Low'], row['Volume']
                range_points = max(1, int((high - low) / self.tick_size))
                vol_per_tick = vol / range_points if range_points > 0 else vol
                
                # Distribute volume across the candle range
                current_p = low
                while current_p <= high:
                    bin_price = round(current_p / self.tick_size) * self.tick_size
                    # Weight middle of the candle slightly more for a bell-curve effect
                    mid_p = (high + low) / 2
                    distance = abs(bin_price - mid_p)
                    weight = 1.0 / (1.0 + distance)
                    
                    added_vol = vol_per_tick * weight
                    liquidity_map[bin_price] = liquidity_map.get(bin_price, 0) + added_vol
                    current_p += self.tick_size

            # Extract the current active map for this timestamp
            candle_heatmap_raw = []
            
            # Calculate dynamic threshold based on the current max depth to avoid sending "cold" zones
            current_max_depth = max(liquidity_map.values()) if liquidity_map else 0
            # Keep only bins that have at least 10% of the max heat, or the hardcoded sensitivity_threshold
            dynamic_threshold = max(self.sensitivity_threshold, current_max_depth * 0.1)

            for price, depth in liquidity_map.items():
                if depth >= dynamic_threshold:
                    candle_heatmap_raw.append((price, depth))
            
            # Sort by depth (hottest first) and cap at 60 bins per candle to prevent JSON bloat
            candle_heatmap_raw.sort(key=lambda x: x[1], reverse=True)
            
            candle_heatmap = [
                {'price': float(p), 'depth': float(d)} 
                for p, d in candle_heatmap_raw[:60]
            ]
                    
            result_data.append({
                'time': current_time,
                'heatmap': candle_heatmap,
                'close': float(row['Close'])
            })

        return {
            'data': result_data,
            'metadata': {
                'tick_size': self.tick_size,
                'decay_factor': self.decay_factor,
                'indicator': 'LiquidityHeatmap'
            }
        }
