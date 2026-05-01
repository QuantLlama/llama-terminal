from ..utils.logger import setup_logger
from ..indicators import (
    calculate_delta, cumulative_delta, delta_divergence,
    detect_key_levels, detect_rejection_candles, vwap,
    detect_imbalance, absorption_detection
)
import pandas as pd
import numpy as np
from typing import Dict, List, Optional

logger = setup_logger('StrategyEngine')


class StrategyEngine:
    def __init__(self, params: Dict = None):
        self.params = params or self.default_params()
        
    def default_params(self) -> Dict:
        """Parámetros por defecto."""
        return {
            'delta_threshold': 100,
            'lookback_period': 10,
            'imbalance_threshold': 0.7,
            'stop_loss_ticks': 8,
            'take_profit_ticks': 12,
            'rr_ratio': 1.5,
            'min_volume': 1000,
            'atr_multiplier': 1.5
        }
    
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Genera señales de trading."""
        signals = data.copy()
        
        signals['delta'] = calculate_delta(signals)
        signals['cum_delta'] = cumulative_delta(signals)
        signals['delta_divergence'] = delta_divergence(signals['last'], signals['delta'])
        
        key_levels = detect_key_levels(signals['high'], signals['low'])
        signals['resistance'] = key_levels['resistance']
        signals['support'] = key_levels['support']
        
        signals['rejection'] = detect_rejection_candles(
            signals['open'], signals['high'], signals['low'], signals['close']
        )
        
        signals['vwap'] = vwap(
            signals['high'], signals['low'], signals['close'], signals['volume']
        )
        
        signals['signal'] = self._evaluate_signals(signals)
        
        return signals
    
    def _evaluate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Evalúa condiciones para generar señales."""
        signals = pd.Series(0, index=data.index)
        
        delta = data['delta']
        cum_delta = data['cum_delta']
        divergence = data['delta_divergence']
        rejection = data['rejection']
        close = data['close'] if 'close' in data.columns else data['last']
        
        for i in range(len(data)):
            if i < self.params['lookback_period']:
                continue
            
            long_conditions = (
                divergence.iloc[i] == 1 and
                cum_delta.iloc[i] > 0 and
                delta.iloc[i] > self.params['delta_threshold']
            )
            
            short_conditions = (
                divergence.iloc[i] == -1 and
                cum_delta.iloc[i] < 0 and
                delta.iloc[i] < -self.params['delta_threshold']
            )
            
            if long_conditions:
                signals.iloc[i] = 1
            elif short_conditions:
                signals.iloc[i] = -1
        
        return signals
    
    def check_entry_conditions(self, current_data: Dict, signal: int) -> bool:
        """Verifica condiciones de entrada adicionales."""
        if signal == 0:
            return False
        
        min_volume = self.params.get('min_volume', 0) if self.params else 0
        if min_volume > 0:
            volume = current_data.get('volume', 0)
            if volume < min_volume:
                logger.debug(f"Volumen insuficiente: {volume}")
                return False
        
        return True
    
    def calculate_exit_levels(self, entry_price: float, direction: str, 
                             atr: float = None) -> Dict[str, float]:
        """Calcula niveles de SL y TP."""
        tick_size = 0.25
        
        if atr:
            sl_distance = atr * self.params['atr_multiplier']
        else:
            sl_distance = self.params['stop_loss_ticks'] * tick_size
        
        if direction.upper() == 'LONG':
            stop_loss = entry_price - sl_distance
            take_profit = entry_price + (sl_distance * self.params['rr_ratio'])
        else:
            stop_loss = entry_price + sl_distance
            take_profit = entry_price - (sl_distance * self.params['rr_ratio'])
        
        return {
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'sl_distance': sl_distance,
            'tp_distance': sl_distance * self.params['rr_ratio']
        }
    
    def should_exit(self, current_price: float, position: Dict, 
                    entry_time: pd.Timestamp = None) -> Optional[str]:
        """Determina si se debe salir de la posición."""
        direction = position['direction']
        stop_loss = position['stop_loss']
        take_profit = position['take_profit']
        
        if direction.upper() == 'LONG':
            if current_price <= stop_loss:
                return 'STOP_LOSS'
            if current_price >= take_profit:
                return 'TAKE_PROFIT'
        else:
            if current_price >= stop_loss:
                return 'STOP_LOSS'
            if current_price <= take_profit:
                return 'TAKE_PROFIT'
        
        return None
