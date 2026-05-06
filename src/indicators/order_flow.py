
import numpy as np
import pandas as pd
from typing import Dict, Any

class OrderFlowIndicator:
    """
    Order Flow Analysis Indicator
    Provides:
    - Approximated Volume Delta (based on body/range ratio)
    - Cumulative Delta
    - VWAP (Volume Weighted Average Price)
    - Imbalance detection (Volume spikes > threshold)
    """

    def __init__(self, config: Dict = None):
        self.config = config or {}
        # Imbalance threshold percentage (e.g. 300%)
        self.imbalance_ratio = float(self.config.get('of_imbalance_ratio', 300)) / 100.0
        
    def calculate(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate Order Flow metrics.
        """
        if len(df) < 50:
            return {'data': []}

        df = df.copy()

        # 1. Delta Calculation (Approximation)
        delta_series = []
        for i in range(len(df)):
            row = df.iloc[i]
            range_val = row['High'] - row['Low']
            
            if range_val <= 0.00001:
                delta_series.append(0)
                continue
                
            body = abs(row['Close'] - row['Open'])
            body_ratio = body / range_val
            
            # Signed by direction
            if row['Close'] > row['Open']:
                delta = row['Volume'] * body_ratio
            else:
                delta = row['Volume'] * -body_ratio
            
            delta_series.append(delta)

        df['delta'] = delta_series
        
        # 2. Cumulative Delta
        # Reset cumulative delta at start of day? For now, continuous from start of data
        df['cumulative_delta'] = df['delta'].cumsum()

        # 3. VWAP (Intraday)
        # We need to reset VWAP at start of each session.
        # Assuming timestamps are available.
        if 'timestamp' in df.columns:
            df['date'] = df['timestamp'].dt.date
        else:
            # Fallback if no timestamp column, just use global cumulative
            df['date'] = 1 
            
        # VWAP = Cumulative(Price * Volume) / Cumulative(Volume)
        df['tp'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['pv'] = df['tp'] * df['Volume']
        df['tp2v'] = (df['tp']**2) * df['Volume']
        
        # Group by date for session VWAP
        df['cumulative_pv'] = df.groupby('date')['pv'].cumsum()
        df['cumulative_tp2v'] = df.groupby('date')['tp2v'].cumsum()
        df['cumulative_vol'] = df.groupby('date')['Volume'].cumsum()
        
        df['vwap'] = df['cumulative_pv'] / df['cumulative_vol']
        df['vwap_var'] = (df['cumulative_tp2v'] / df['cumulative_vol']) - (df['vwap']**2)
        df['vwap_std'] = np.sqrt(df['vwap_var'].clip(lower=0))
        
        df['vwap_upper_1'] = df['vwap'] + df['vwap_std']
        df['vwap_lower_1'] = df['vwap'] - df['vwap_std']
        df['vwap_upper_2'] = df['vwap'] + 2 * df['vwap_std']
        df['vwap_lower_2'] = df['vwap'] - 2 * df['vwap_std']

        # 4. Imbalances (Volume Spikes)
        # Volume > SMA(20) * Ratio
        df['vol_sma'] = df['Volume'].rolling(20).mean()
        df['imbalance'] = df['Volume'] > (df['vol_sma'] * self.imbalance_ratio)
        
        # Prepare result data
        result_data = []
        
        # timestamps to int/unix
        if 'timestamp' in df.columns:
            times = df['timestamp'].values.astype(np.int64) // 10**9 # seconds
        elif 'time' in df.columns:
            times = df['time'].values
        else:
            times = df.index.values

        for i in range(len(df)):
            if i < 20: continue # Skip warmup

            row = df.iloc[i]
            
            item = {
                'time': int(times[i]),
                'delta': float(row['delta']),
                'cumulative_delta': float(row['cumulative_delta']),
                'vwap': float(row['vwap']) if not pd.isna(row['vwap']) else None,
                'vwap_u1': float(row['vwap_upper_1']) if not pd.isna(row['vwap_upper_1']) else None,
                'vwap_l1': float(row['vwap_lower_1']) if not pd.isna(row['vwap_lower_1']) else None,
                'vwap_u2': float(row['vwap_upper_2']) if not pd.isna(row['vwap_upper_2']) else None,
                'vwap_l2': float(row['vwap_lower_2']) if not pd.isna(row['vwap_lower_2']) else None,
                'imbalance': bool(row['imbalance'])
            }
            result_data.append(item)

        return {
            'data': result_data,
            'metadata': {
                'imbalance_ratio': self.imbalance_ratio
            }
        }
