from datetime import datetime
import pandas as pd

class pelito:
    def __init__(self):
        self.metadata = {
            'name': 'Estrategia NQ Medias Móviles',
            'description': 'Estrategia de cruce de medias móviles para operar micro futuros del Nasdaq (NQ) a corto plazo.',
            'params': {
                'fast_ma_period': 9,
                'slow_ma_period': 25,
                'take_profit_multiplier': 0.006, # Ajustado TP a 0.6%
                'stop_loss_multiplier': 0.003 # Ajustado SL a 0.3%
            }
        }
        self.position = None

    def update(self, df: pd.DataFrame):
        # --- PARÁMETROS ---
        fast_ma_period = self.metadata['params']['fast_ma_period']
        slow_ma_period = self.metadata['params']['slow_ma_period']
        take_profit_multiplier = self.metadata['params']['take_profit_multiplier']
        stop_loss_multiplier = self.metadata['params']['stop_loss_multiplier']

        # --- ESCRIBE TU CÓDIGO ---
        if len(df) < slow_ma_period + 1:
            return 'HOLD', {}

        df['Fast_MA'] = df['Close'].rolling(window=fast_ma_period).mean()
        df['Slow_MA'] = df['Close'].rolling(window=slow_ma_period).mean()

        last_fast_ma = df['Fast_MA'].iloc[-1]
        last_slow_ma = df['Slow_MA'].iloc[-1]
        prev_fast_ma = df['Fast_MA'].iloc[-2]
        prev_slow_ma = df['Slow_MA'].iloc[-2]
        current_price = df['Close'].iloc[-1]

        signal = 'HOLD'
        metadata = {}

        if self.position:
            entry_price = self.position['entry_price']
            position_type = self.position['type']

            if position_type == 'BUY':
                take_profit = entry_price * (1 + take_profit_multiplier)
                stop_loss = entry_price * (1 - stop_loss_multiplier)

                if current_price >= take_profit:
                    signal = 'SELL'
                    metadata = {'exit_type': 'Take Profit', 'entry_price': entry_price, 'exit_price': current_price, 'position_type': position_type}
                    self.position = None
                elif current_price <= stop_loss:
                    signal = 'SELL'
                    metadata = {'exit_type': 'Stop Loss', 'entry_price': entry_price, 'exit_price': current_price, 'position_type': position_type}
                    self.position = None

            elif position_type == 'SELL':
                take_profit = entry_price * (1 - take_profit_multiplier)
                stop_loss = entry_price * (1 + stop_loss_multiplier)

                if current_price <= take_profit:
                    signal = 'BUY'
                    metadata = {'exit_type': 'Take Profit', 'entry_price': entry_price, 'exit_price': current_price, 'position_type': position_type}
                    self.position = None
                elif current_price >= stop_loss:
                    signal = 'BUY'
                    metadata = {'exit_type': 'Stop Loss', 'entry_price': entry_price, 'exit_price': current_price, 'position_type': position_type}
                    self.position = None

        if not self.position:
            if prev_fast_ma < prev_slow_ma and last_fast_ma > last_slow_ma:
                signal = 'BUY'
                self.position = {'type': 'BUY', 'entry_price': current_price, 'timestamp': datetime.now().isoformat()}
                metadata = {'entry_price': current_price, 'timestamp': datetime.now().isoformat(), 'position_type': 'BUY'}

            elif prev_fast_ma > prev_slow_ma and last_fast_ma < last_slow_ma:
                signal = 'SELL'
                self.position = {'type': 'SELL', 'entry_price': current_price, 'timestamp': datetime.now().isoformat()}
                metadata = {'entry_price': current_price, 'timestamp': datetime.now().isoformat(), 'position_type': 'SELL'}

        return signal, metadata