import pandas as pd
import numpy as np
from typing import Dict, List
from ..utils.logger import setup_logger

logger = setup_logger('Metrics')


def calculate_trading_metrics(trades: List[Dict], equity_curve: List[float],
                             initial_balance: float) -> Dict:
    """Calcula métricas completas de trading."""
    if not trades:
        return get_empty_metrics()
    
    pnls = [t['pnl'] for t in trades]
    total_pnl = sum(pnls)
    
    winning_trades = [p for p in pnls if p > 0]
    losing_trades = [p for p in pnls if p < 0]
    
    win_rate = len(winning_trades) / len(trades)
    avg_win = np.mean(winning_trades) if winning_trades else 0
    avg_loss = np.mean(losing_trades) if losing_trades else 0
    
    profit_factor = abs(sum(winning_trades) / sum(losing_trades)) if losing_trades else 0
    
    equity_series = pd.Series(equity_curve)
    max_equity = equity_series.cummax()
    drawdown = (max_equity - equity_series)
    max_drawdown = drawdown.max() / initial_balance
    
    returns = equity_series.pct_change().dropna()
    sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0
    
    calmar_ratio = (total_pnl / initial_balance) / max_drawdown if max_drawdown > 0 else 0
    
    max_consecutive_wins = _max_consecutive([1 if p > 0 else 0 for p in pnls])
    max_consecutive_losses = _max_consecutive([1 if p < 0 else 0 for p in pnls])
    
    return {
        'total_trades': len(trades),
        'total_pnl': total_pnl,
        'total_pnl_pct': (total_pnl / initial_balance) * 100,
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'sharpe_ratio': sharpe_ratio,
        'max_drawdown': max_drawdown,
        'calmar_ratio': calmar_ratio,
        'max_consecutive_wins': max_consecutive_wins,
        'max_consecutive_losses': max_consecutive_losses,
        'avg_r_multiple': _calculate_avg_r_multiple(trades)
    }


def get_empty_metrics() -> Dict:
    """Retorna métricas vacías."""
    return {
        'total_trades': 0,
        'total_pnl': 0,
        'total_pnl_pct': 0,
        'win_rate': 0,
        'avg_win': 0,
        'avg_loss': 0,
        'profit_factor': 0,
        'sharpe_ratio': 0,
        'max_drawdown': 0,
        'calmar_ratio': 0,
        'max_consecutive_wins': 0,
        'max_consecutive_losses': 0,
        'avg_r_multiple': 0
    }


def _max_consecutive(values: List[int]) -> int:
    """Calcula máximo de valores consecutivos."""
    max_count = 0
    current_count = 0
    
    for v in values:
        if v == 1:
            current_count += 1
            max_count = max(max_count, current_count)
        else:
            current_count = 0
    
    return max_count


def _calculate_avg_r_multiple(trades: List[Dict]) -> float:
    """Calcula promedio de múltiplo R."""
    if not trades:
        return 0
    
    r_multiples = []
    
    for trade in trades:
        if 'risk' in trade and trade['risk'] != 0:
            r_multiples.append(trade['pnl'] / trade['risk'])
    
    return np.mean(r_multiples) if r_multiples else 0


def generate_trade_report(trades: List[Dict], metrics: Dict) -> str:
    """Genera reporte de trades."""
    report = []
    report.append("=" * 60)
    report.append("REPORTE DE BACKTESTING")
    report.append("=" * 60)
    report.append("\nMÉTRICAS:")
    report.append("-" * 60)
    
    for key, value in metrics.items():
        if isinstance(value, float):
            report.append(f"{key:25s}: {value:10.4f}")
        else:
            report.append(f"{key:25s}: {value}")
    
    if trades:
        report.append("\nÚLTIMOS 5 TRADES:")
        report.append("-" * 60)
        
        for trade in trades[-5:]:
            direction = trade['direction']
            entry = trade['entry_price']
            exit_price = trade['exit_price']
            pnl = trade['pnl']
            
            report.append(f"{direction:6s} | Entry: {entry:8.2f} | Exit: {exit_price:8.2f} | PnL: ${pnl:8.2f}")
    
    report.append("\n" + "=" * 60)
    
    return "\n".join(report)
