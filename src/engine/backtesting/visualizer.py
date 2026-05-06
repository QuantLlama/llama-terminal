import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from typing import Dict, List
from ..utils.logger import setup_logger

logger = setup_logger('Visualizer')


def plot_equity_curve(equity_curve: List[float], save_path: str = None):
    """Grafica curva de equity."""
    plt.figure(figsize=(12, 6))
    plt.plot(equity_curve, label='Equity', linewidth=2)
    plt.title('Curva de Equity')
    plt.xlabel('Periodos')
    plt.ylabel('Balance ($)')
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        logger.info(f"Gráfico guardado en: {save_path}")
    
    plt.show()


def plot_drawdown(equity_curve: List[float], save_path: str = None):
    """Grafica drawdown."""
    equity_series = pd.Series(equity_curve)
    max_equity = equity_series.cummax()
    drawdown = (max_equity - equity_series) / max_equity * 100
    
    plt.figure(figsize=(12, 6))
    plt.fill_between(range(len(drawdown)), drawdown, alpha=0.3, color='red')
    plt.plot(drawdown, color='red', linewidth=2)
    plt.title('Drawdown (%)')
    plt.xlabel('Periodos')
    plt.ylabel('Drawdown (%)')
    plt.grid(True, alpha=0.3)
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        logger.info(f"Gráfico guardado en: {save_path}")
    
    plt.show()


def plot_interactive_dashboard(trades: List[Dict], equity_curve: List[float], 
                                signals: pd.DataFrame = None):
    """Crea dashboard interactivo con Plotly."""
    fig = make_subplots(
        rows=3, cols=2,
        subplot_titles=('Equity Curve', 'Drawdown', 'Trades PnL', 
                       'Win Rate Distribution', 'Cumulative PnL', 'Trade Count'),
        specs=[[{"secondary_y": True}, {"secondary_y": True}],
               [{"secondary_y": False}, {"secondary_y": False}],
               [{"secondary_y": False}, {"secondary_y": False}]]
    )
    
    equity_series = pd.Series(equity_curve)
    max_equity = equity_series.cummax()
    drawdown = (max_equity - equity_series) / max_equity * 100
    
    fig.add_trace(
        go.Scatter(y=equity_curve, name='Equity', line=dict(color='blue')),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Scatter(y=drawdown, fill='tozeroy', name='Drawdown', 
                   line=dict(color='red')),
        row=1, col=2
    )
    
    if trades:
        pnls = [t['pnl'] for t in trades]
        cumulative_pnl = pd.Series(pnls).cumsum()
        
        colors = ['green' if pnl >= 0 else 'red' for pnl in pnls]
        
        fig.add_trace(
            go.Bar(y=pnls, marker_color=colors, name='PnL'),
            row=2, col=1
        )
        
        win_rate = sum(1 for pnl in pnls if pnl > 0) / len(pnls) * 100
        fig.add_trace(
            go.Pie(labels=['Wins', 'Losses'], 
                   values=[win_rate, 100-win_rate]),
            row=2, col=2
        )
        
        fig.add_trace(
            go.Scatter(y=cumulative_pnl, name='Cumulative PnL', 
                       line=dict(color='purple')),
            row=3, col=1
        )
        
        fig.add_trace(
            go.Scatter(y=range(len(trades)), name='Trade Count'),
            row=3, col=2
        )
    
    fig.update_layout(
        title_text='Dashboard de Backtesting',
        showlegend=False,
        height=1200
    )
    
    fig.show()
    logger.info("Dashboard interactivo generado")


def plot_trades_analysis(trades: List[Dict], save_path: str = None):
    """Analiza y grafica trades."""
    if not trades:
        logger.warning("No hay trades para analizar")
        return
    
    pnls = [t['pnl'] for t in trades]
    holding_periods = []
    
    for i, trade in enumerate(trades):
        if i > 0:
            holding_period = trade.get('exit_index', i) - trade.get('entry_index', i)
            holding_periods.append(holding_period)
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    colors = ['green' if pnl >= 0 else 'red' for pnl in pnls]
    
    axes[0, 0].bar(range(len(pnls)), pnls, color=colors)
    axes[0, 0].set_title('PnL por Trade')
    axes[0, 0].set_xlabel('Trade #')
    axes[0, 0].set_ylabel('PnL ($)')
    axes[0, 0].grid(True, alpha=0.3)
    
    axes[0, 1].hist(pnls, bins=30, color='blue', alpha=0.7)
    axes[0, 1].set_title('Distribución de PnL')
    axes[0, 1].set_xlabel('PnL ($)')
    axes[0, 1].set_ylabel('Frecuencia')
    axes[0, 1].grid(True, alpha=0.3)
    
    if holding_periods:
        axes[1, 0].scatter(holding_periods, pnls, alpha=0.6)
        axes[1, 0].set_title('PnL vs Periodo de Tenencia')
        axes[1, 0].set_xlabel('Periodo (barras)')
        axes[1, 0].set_ylabel('PnL ($)')
        axes[1, 0].grid(True, alpha=0.3)
    
    cumulative_pnl = pd.Series(pnls).cumsum()
    axes[1, 1].plot(cumulative_pnl, linewidth=2, color='purple')
    axes[1, 1].set_title('PnL Acumulado')
    axes[1, 1].set_xlabel('Trade #')
    axes[1, 1].set_ylabel('PnL Acumulado ($)')
    axes[1, 1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        logger.info(f"Gráfico guardado en: {save_path}")
    
    plt.show()
