from ..core.strategy_engine import StrategyEngine
from ..core.risk_manager import RiskManager
from ..risk_math import profit_factor
from ..utils.logger import setup_logger
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple

logger = setup_logger('Backtester')


class Backtester:
    def __init__(self, data: pd.DataFrame, initial_balance: float = 10000, strategy_class=None, tick_size=0.25, tick_value=0.5, ignore_filters=False):
        self.data = data.copy()
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.positions = []
        self.trades = []
        self.equity_curve = [initial_balance]
        self.strategy_class = strategy_class
        self.tick_size = tick_size
        self.tick_value = tick_value
        self.ignore_filters = ignore_filters
        
    def run(self, strategy_params: Dict = None) -> Dict:
        """Ejecuta backtesting con parámetros dados y logging detallado."""
        logger.info("Iniciando backtesting...")
        
        self.balance = self.initial_balance
        self.equity_curve = [self.initial_balance]
        self.trades = []
        
        risk_manager = RiskManager(self.balance)
        if self.strategy_class is not None:
            strategy = self.strategy_class(strategy_params)
        else:
            strategy = StrategyEngine(strategy_params)
        
        # Inyectar ignore_filters en la estrategia si es compatible
        if hasattr(strategy, 'params'):
            strategy.params['ignore_filters'] = self.ignore_filters
        
        signals = strategy.generate_signals(self.data)
        
        # Logging de estadísticas de señales
        total_signals = (signals['signal'].abs() > 0).sum()
        logger.info(f"Señales generadas: {total_signals}")
        
        position = None
        signals_filtered = 0
        
        for i, row in signals.iterrows():
            current_price = row.get('close', row.get('last', 0))
            signal = row.get('signal', 0)
            
            if position is None and signal != 0:
                entry_conditions = {
                    'volume': row.get('volume', 0)
                }
                
                if strategy.check_entry_conditions(entry_conditions, signal):
                    direction = 'LONG' if signal > 0 else 'SHORT'
                    stop_loss, take_profit = self._calculate_exit_levels(
                        strategy, current_price, direction, row
                    )
                    
                    contracts = risk_manager.calculate_position_size(
                        current_price, stop_loss
                    )
                    
                    position = {
                        'direction': direction,
                        'entry_price': current_price,
                        'contracts': contracts,
                        'stop_loss': stop_loss,
                        'take_profit': take_profit,
                        'entry_index': i,
                        'entry_time': i
                    }
            
            elif position:
                exit_reason = strategy.should_exit(
                    current_price, position
                )
                
                if exit_reason:
                    pnl = self._calculate_pnl(position, current_price)
                    self.balance += pnl
                    
                    trade = {
                        'direction': position['direction'],
                        'entry_price': position['entry_price'],
                        'entry_time': position['entry_time'],
                        'exit_price': current_price,
                        'exit_time': i,
                        'contracts': position['contracts'],
                        'pnl': pnl,
                        'exit_reason': exit_reason
                    }
                    
                    self.trades.append(trade)
                    position = None
                    risk_manager.update_balance(self.balance)
            
            self.equity_curve.append(self.balance)
        
        metrics = self.calculate_metrics()
        
        # Logging detallado de resultados
        logger.info(f"Trades ejecutados: {metrics['total_trades']}")
        logger.info(f"Win Rate: {metrics['win_rate']:.1%}")
        logger.info(f"Total PnL: ${metrics['total_pnl']:.2f}")
        logger.info(f"Sharpe Ratio: {metrics['sharpe_ratio']:.3f}")
        logger.info(f"Max Drawdown: {metrics['max_drawdown']:.2%}")
        logger.info(f"Profit Factor: {metrics['profit_factor']:.2f}")
        
        return metrics
    
    def _calculate_exit_levels(self, strategy, 
                               entry_price: float, direction: str,
                               row: pd.Series) -> Tuple[float, float]:
        """Calcula niveles de salida."""
        if 'stop_loss' in row and 'take_profit' in row and pd.notna(row['stop_loss']):
            return row['stop_loss'], row['take_profit']
            
        atr = row.get('atr', None)
        levels = strategy.calculate_exit_levels(entry_price, direction, atr)
        return levels['stop_loss'], levels['take_profit']
    
    def _calculate_pnl(self, position: Dict, exit_price: float) -> float:
        """Calcula PnL del trade basado en tick_size y tick_value."""
        if position['direction'] == 'LONG':
            price_diff = exit_price - position['entry_price']
        else:
            price_diff = position['entry_price'] - exit_price
        
        ticks = price_diff / self.tick_size
        return ticks * position['contracts'] * self.tick_value
    
    def calculate_metrics(self) -> Dict:
        """Calcula métricas del backtesting."""
        if not self.trades:
            return {
                'total_trades': 0,
                'total_pnl': 0,
                'win_rate': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'profit_factor': 0
            }
        
        pnls = [t['pnl'] for t in self.trades]
        winning_trades = [p for p in pnls if p > 0]
        losing_trades = [p for p in pnls if p < 0]
        
        total_pnl = sum(pnls)
        win_rate = len(winning_trades) / len(self.trades)
        
        pf = profit_factor(winning_trades, losing_trades)
        
        equity_series = pd.Series(self.equity_curve)
        max_drawdown = (equity_series.cummax() - equity_series).max() / self.initial_balance
        
        returns = equity_series.pct_change().dropna()
        sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0
        
        return {
            'total_trades': len(self.trades),
            'total_pnl': total_pnl,
            'win_rate': win_rate,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'profit_factor': pf,
            'avg_win': np.mean(winning_trades) if winning_trades else 0,
            'avg_loss': np.mean(losing_trades) if losing_trades else 0
        }
