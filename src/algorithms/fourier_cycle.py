import numpy as np
import pandas as pd
from datetime import datetime

class FourierCycleStrategy:
    """
    Port of FourierMNQSystem from NinjaTrader.
    Uses FFT to detect market cycles and project future price movement.
    """
    def __init__(self, config=None):
        if config is None:
            config = {}
        
        # Strategy Parameters (NinjaTrader defaults)
        self.fourier_period = config.get('fourier_period', 120)
        self.harmonics_count = config.get('harmonics_count', 8)
        self.projection_bars = config.get('projection_bars', 20)
        self.signal_threshold = config.get('signal_threshold', 0.5)
        self.cooldown_bars = config.get('cooldown_bars', 5)
        
        # Risk Parameters
        self.reward_ratio = config.get('reward_ratio', 2.5)
        self.position_size = config.get('position_size', 1)
        
        # State
        self.bars_since_last_trade = 0
        self.last_signal = 'HOLD'
        self.reconstructed_wave = []
        self.cycle_projection = 0
        self.dominant_harmonics = []
        self.momentum_score = 0
        
    def perform_fft(self, prices):
        """Calculates FFT and extracts power spectrum components."""
        # Subtract mean (normalization)
        mean_price = np.mean(prices)
        normalized = prices - mean_price
        
        # Apply Hamming Window
        window = np.hamming(len(normalized))
        windowed = normalized * window
        
        # FFT
        fft_vals = np.fft.fft(windowed)
        # Power Spectrum (magnitude)
        power_spectrum = np.abs(fft_vals)[:len(fft_vals)//2]
        
        return fft_vals, power_spectrum, mean_price

    def extract_harmonics(self, fft_vals, power_spectrum):
        """Identifies dominant cycle peaks in the power spectrum."""
        n = self.fourier_period
        harmonics = []
        
        # Find local peaks in power spectrum (ignoring very low frequencies and DC)
        # Starting from index 3 as per NinjaTrader code
        for i in range(3, len(power_spectrum) - 2):
            if (power_spectrum[i] > power_spectrum[i-1] and 
                power_spectrum[i] > power_spectrum[i+1] and
                power_spectrum[i] > power_spectrum[i-2] and
                power_spectrum[i] > power_spectrum[i+2]):
                
                freq = i / n
                amp = power_spectrum[i] * 2.0 / n
                phase = np.angle(fft_vals[i])
                period = n / i
                power = power_spectrum[i]
                
                harmonics.append({
                    'freq': freq,
                    'amp': amp,
                    'phase': phase,
                    'period': period,
                    'power': power
                })
        
        # Sort by power and take top N
        harmonics = sorted(harmonics, key=lambda x: x['power'], reverse=True)[:self.harmonics_count]
        # Then sort by frequency
        harmonics = sorted(harmonics, key=lambda x: x['freq'])
        
        return harmonics

    def reconstruct_waveform(self, harmonics):
        """Sum harmonics to project future price movement."""
        n = self.fourier_period
        wave = []
        
        for t in range(self.projection_bars):
            val = 0
            for h in harmonics:
                # angle = 2.0 * PI * freq * (N + t) + phase
                angle = 2.0 * np.pi * h['freq'] * (n + t) + h['phase']
                val += h['amp'] * np.cos(angle)
            wave.append(val)
            
        return wave

    def update(self, df):
        """
        Main entry point for strategy.
        Expects a DataFrame with 'Close', 'EMA_Fast', 'EMA_Slow', 'RSI', 'ATR'.
        """
        if len(df) < self.fourier_period:
            return 'HOLD', {}

        # 1. Prepare Data
        prices = df['Close'].tail(self.fourier_period).values
        last_close = prices[-1]

        # 2. Fourier Analysis
        fft_vals, power_spectrum, _ = self.perform_fft(prices)
        self.dominant_harmonics = self.extract_harmonics(fft_vals, power_spectrum)
        
        if not self.dominant_harmonics:
            return 'HOLD', {}

        # 3. Waveform Reconstruction & Projection
        self.reconstructed_wave = self.reconstruct_waveform(self.dominant_harmonics)
        
        # Weighted average of first few projection points (as per NinjaTrader)
        raw_proj = 0
        total_weight = 0
        for i in range(min(5, self.projection_bars)):
            weight = 1.0 / (i + 1)
            raw_proj += self.reconstructed_wave[i] * weight
            total_weight += weight
            
        self.cycle_projection = (raw_proj / total_weight) + last_close

        # 4. Trend & Momentum Indicators
        # Calculate missing indicators if necessary
        if 'EMA_Fast' not in df.columns:
            df['EMA_Fast'] = df['Close'].ewm(span=8, adjust=False).mean()
        if 'EMA_Slow' not in df.columns:
            df['EMA_Slow'] = df['Close'].ewm(span=21, adjust=False).mean()
        
        ema_fast = df['EMA_Fast'].iloc[-1]
        ema_slow = df['EMA_Slow'].iloc[-1]
        rsi = df['RSI'].iloc[-1]
        atr = df['ATR'].iloc[-1]
        
        # Calculations from NinjaTrader:
        # rsiScore = (rsi - 50) / 50.0;
        # cycleScore = (cycleProjection - Close[0]) / Close[0] * 100;
        # trendScore = (emaFast - emaSlow) / Close[0] * 100;
        # momentumScore = (cycleScore * 0.65) + (rsiScore * 0.15) + (trendScore * 0.20);
        
        rsi_score = (rsi - 50) / 50.0
        cycle_score = (self.cycle_projection - last_close) / last_close * 100
        trend_score = (ema_fast - ema_slow) / last_close * 100
        
        self.momentum_score = (cycle_score * 0.65) + (rsi_score * 0.15) + (trend_score * 0.20)

        # 5. Signal Generation
        # Conditions (Mirroring NinjaTrader logic):
        cycle_bullish = self.cycle_projection > last_close
        cycle_bearish = self.cycle_projection < last_close
        trend_bullish = ema_fast > ema_slow
        trend_bearish = ema_fast < ema_slow
        
        change_pct = abs(self.cycle_projection - last_close) / last_close * 100
        significant_move = change_pct > (self.signal_threshold / 10.0)
        
        # Hardcoding tick size to match NT logic (for MNQ = 0.25, but we use ATR)
        # good_volatility = atr > TickSize * 10;
        # Assuming we just need some minimum volatility
        good_volatility = atr > 0
        
        not_overbought = rsi < 75
        not_oversold = rsi > 25
        
        signal = 'HOLD'
        
        # ENTRADA LONG
        if (cycle_bullish and trend_bullish and significant_move and good_volatility and 
            not_overbought and self.momentum_score > (self.signal_threshold / 10.0)):
            if self.bars_since_last_trade >= self.cooldown_bars:
                signal = 'BUY'
        
        # ENTRADA SHORT
        elif (cycle_bearish and trend_bearish and significant_move and good_volatility and 
              not_oversold and self.momentum_score < -(self.signal_threshold / 10.0)):
            if self.bars_since_last_trade >= self.cooldown_bars:
                signal = 'SELL'

        # Update state
        if signal != 'HOLD':
            self.bars_since_last_trade = 0
        else:
            self.bars_since_last_trade += 1
            
        self.last_signal = signal
        
        # Prepare trend/reconstruction data with timestamps
        # CRITICAL: Use the MOST RECENT timestamps from the DataFrame
        # These should match the visible range on the chart
        if 'timestamp' in df.columns:
            # Get the LAST fourier_period timestamps (most recent bars)
            last_times = df['timestamp'].iloc[-self.fourier_period:].values
        elif 'time' in df.columns:
             # MT5Connector returns 'time' column
            last_times = df['time'].iloc[-self.fourier_period:].values
        elif hasattr(df.index, 'to_pydatetime'):
            last_times = df.index[-self.fourier_period:]
        else:
            # STRICT MODE: No synthetic data allowed
            raise ValueError("Critical: No valid time column ('timestamp' or 'time') or DatetimeIndex found in DataFrame. Real market data is required.")

        # Convert to Unix timestamps (seconds)
        # This is REQUIRED for the frontend to match with the chart
        times_unix = [int(pd.Timestamp(t).timestamp()) for t in last_times]

        



        # Historical Reconstruction
        # Calculate the raw wave first
        full_wave_raw = []
        for t in range(self.fourier_period):
             val = 0
             for h in self.dominant_harmonics:
                 angle = 2.0 * np.pi * h['freq'] * t + h['phase']
                 val += h['amp'] * np.cos(angle)
             full_wave_raw.append(val)
        
        # CRITICAL FIX: Align the reconstruction so the LAST point matches the current price
        # This ensures the reconstruction "catches up" to the actual market
        raw_last_value = full_wave_raw[-1]
        alignment_offset = last_close - raw_last_value
        
        # Apply alignment to all points
        full_wave = [v + alignment_offset for v in full_wave_raw]
        
        reconstruction = []
        for i in range(len(times_unix)):
            reconstruction.append({'time': times_unix[i], 'value': float(full_wave[i])})

        # Future Projection
        projection = []
        # Calculate future timestamps
        if len(times_unix) > 1:
            step = times_unix[-1] - times_unix[-2]
        else:
            step = 60 # Default 1m
        
        # CRITICAL FIX: Ensure projection starts from the LAST reconstruction point
        # This creates visual continuity (no gap between cyan and yellow lines)
        projection_base = full_wave[-1]  # Last point of reconstruction
        
        for i in range(len(self.reconstructed_wave)):
            future_t = times_unix[-1] + (step * (i + 1))
            # Project from the last reconstruction point, not from last_close
            projection_value = projection_base + self.reconstructed_wave[i]
            projection.append({'time': future_t, 'value': float(projection_value)})


        # Metadata for plots
        # Generate harmonic bands with points for visualization
        harmonic_bands = []
        for h in self.dominant_harmonics:
            band_points = []
            # Calculate raw harmonic wave
            raw_harmonic = []
            for i in range(len(times_unix)):
                t = i
                angle = 2.0 * np.pi * h['freq'] * t + h['phase']
                raw_value = h['amp'] * np.cos(angle)
                raw_harmonic.append(raw_value)
            
            # CRITICAL FIX: Align harmonic bands to current price
            # Use the same alignment offset as the main reconstruction
            harmonic_last = raw_harmonic[-1]
            harmonic_offset = last_close - harmonic_last
            
            for i in range(len(times_unix)):
                aligned_value = raw_harmonic[i] + harmonic_offset
                band_points.append({'time': times_unix[i], 'value': float(aligned_value)})
            
            harmonic_bands.append({
                'freq': h['freq'],
                'amp': h['amp'],
                'phase': h['phase'],
                'points': band_points
            })
        
        metadata = {
            'projection': projection,
            'reconstruction': reconstruction,
            'momentum_score': float(self.momentum_score),
            'harmonics': harmonic_bands,
            'status': 'BULLISH' if self.momentum_score > (self.signal_threshold / 10.0) else 
                      'BEARISH' if self.momentum_score < -(self.signal_threshold / 10.0) else 'NEUTRAL'
        }
        
        return signal, metadata
