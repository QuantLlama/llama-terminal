import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler

class FourierStrategy:
    def __init__(self, high_pass_cutoff=0.01, low_pass_cutoff=0.5, entry_threshold=0.1, exit_threshold=-0.1, config=None):
        if config:
            self.high_pass_cutoff = float(config.get('high_pass_cutoff', 0.01))
            self.low_pass_cutoff = float(config.get('low_pass_cutoff', 0.5))
            self.entry_threshold = float(config.get('entry_threshold', 0.1))
            self.exit_threshold = float(config.get('exit_threshold', -0.1))
        else:
            self.high_pass_cutoff = high_pass_cutoff
            self.low_pass_cutoff = low_pass_cutoff
            self.entry_threshold = entry_threshold
            self.exit_threshold = exit_threshold
            
        self.scaler = StandardScaler()

    def apply_fourier_filter(self, series):
        n = len(series)
        if n < 2:
            return pd.Series(np.zeros(2) if n==1 else [], index=series.index) # Ajuste para devolver al menos dos valores si hay uno solo para evitar errores en `iloc[-2]`
        
        fft_result = np.fft.fft(series.values)
        frequencies = np.fft.fftfreq(n)

        fft_result[np.abs(frequencies) < self.high_pass_cutoff] = 0
        fft_result[np.abs(frequencies) > self.low_pass_cutoff] = 0
        
        filtered_series = np.fft.ifft(fft_result).real
        return pd.Series(filtered_series, index=series.index)

    def update(self, df):
        if df.empty or len(df) < 20:
            return "HOLD", {"status": "waiting_data", "reason": f"DataFrame vacío o con menos de 20 entradas ({len(df)})."}

        if "Close" not in df.columns:
            return "HOLD", {"status": "missing_close_column", "reason": "La columna 'Close' no está presente en el DataFrame."}

        close_prices = df["Close"].values.reshape(-1, 1)

        if len(close_prices) == 0:
            return "HOLD", {"status": "no_sufficient_close_data", "reason": "No hay datos de precios de cierre válidos."}
            
        try:
            self.scaler.fit(close_prices)
            normalized_close = self.scaler.transform(close_prices).flatten()
            normalized_close_series = pd.Series(normalized_close)
        except Exception as e:
            return "HOLD", {"status": "scaler_error", "reason": f"Error al normalizar los datos: {str(e)}"}

        filtered_signal = self.apply_fourier_filter(normalized_close_series)
        
        if filtered_signal.empty or len(filtered_signal) < 2 : # Se requiere al menos dos valores para curr_val y prev_val
            return "HOLD", {"status": "filtered_signal_empty", "reason": "La señal filtrada está vacía o es demasiado corta después del procesamiento Fourier."}
            
        curr_val = filtered_signal.iloc[-1]
        prev_val = filtered_signal.iloc[-2] 

        signal = "HOLD"
        if prev_val < self.entry_threshold and curr_val >= self.entry_threshold:
            signal = "BUY"
        elif prev_val > self.exit_threshold and curr_val <= self.exit_threshold:
            signal = "SELL"

        metadata = {
            "fourier_val": float(curr_val),
            "entry_threshold": self.entry_threshold,
            "exit_threshold": self.exit_threshold,
            "status": "ok"
        }

        return signal, metadata