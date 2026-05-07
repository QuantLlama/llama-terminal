from ..utils.logger import setup_logger
from ..utils import is_trading_session, CONFIG
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime

logger = setup_logger('DataManager')


class DataManager:
    def __init__(self):
        self.tick_data = pd.DataFrame()
        self.bar_data = pd.DataFrame()
        self.current_tick = None
        
    def update_tick(self, tick: Dict):
        """Actualiza datos con nuevo tick."""
        self.current_tick = tick
        
        new_tick = pd.DataFrame([tick])
        self.tick_data = pd.concat([self.tick_data, new_tick], ignore_index=True)
        
        logger.debug(f"Tick actualizado: {tick.get('symbol')} @ {tick.get('last')}")
    
    def get_tick(self) -> Optional[Dict]:
        """Obtiene tick actual."""
        return self.current_tick
    
    def get_recent_ticks(self, n: int = 100) -> pd.DataFrame:
        """Obtiene últimos n ticks."""
        if len(self.tick_data) < n:
            return self.tick_data
        return self.tick_data.tail(n)
    
    def aggregate_bars(self, timeframe: str = '1T') -> pd.DataFrame:
        """Agrega ticks en barras OHLCV."""
        if 'timestamp' not in self.tick_data.columns:
            return pd.DataFrame()
        
        tick_data = self.tick_data.copy()
        tick_data['timestamp'] = pd.to_datetime(tick_data['timestamp'])
        tick_data = tick_data.set_index('timestamp')
        
        bars = tick_data.resample(timeframe).agg({
            'last': ['first', 'max', 'min', 'last'],
            'volume': 'sum'
        }).dropna()
        
        bars.columns = ['open', 'high', 'low', 'close', 'volume']
        bars = bars.reset_index()
        
        self.bar_data = bars
        return bars
    
    def is_trading_allowed(self) -> bool:
        """Verifica si trading está permitido."""
        if not is_trading_session('US_RTH'):
            logger.debug("Fuera de sesión de trading permitida")
            return False
        
        return True
    
    def get_market_status(self) -> Dict:
        """Obtiene estado actual del mercado."""
        tick = self.get_tick()
        
        if not tick:
            return {
                'status': 'NO_DATA',
                'timestamp': datetime.now()
            }
        
        recent_ticks = self.get_recent_ticks(20)
        
        if len(recent_ticks) < 20:
            volatility = 0
        else:
            price_range = recent_ticks['last'].max() - recent_ticks['last'].min()
            volatility = price_range
            
        return {
            'status': 'ACTIVE' if self.is_trading_allowed() else 'CLOSED',
            'symbol': tick.get('symbol'),
            'price': tick.get('last'),
            'volume': tick.get('volume'),
            'volatility': volatility,
            'timestamp': datetime.now()
        }
    
    def clear_old_data(self, max_ticks: int = 10000):
        """Limpia datos antiguos para mantener memoria controlada."""
        if len(self.tick_data) > max_ticks:
            self.tick_data = self.tick_data.tail(max_ticks)
            logger.debug(f"Datos antiguos limpiados, manteniendo últimos {max_ticks} ticks")
