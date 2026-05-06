import pandas as pd
import numpy as np


class Backtester:
    """Backtester con costos de transacción reales y métricas profesionales.

    Los costos se descuentan en cada trade (ida y vuelta), incluyendo spread
    y comisión por contrato/lote. Esto da resultados más honestos que
    un backtest sin fricción.
    """

    # Costos por defecto por tipo de activo (porcentaje ida y vuelta)
    DEFAULT_COSTS = {
        'Futures':  0.0008,   # ~$0.80 por contrato micro (spread + comisión)
        'Stocks':   0.0010,   # ~0.10% entre spread y comisiones
        'Crypto':   0.0020,   # ~0.20% taker fee (ida + vuelta)
        'ETF':      0.0006,   # ETFs líquidos tienen spread bajo
        'Forex':    0.0003,   # Spread en pares principales
    }

    def __init__(self, initial_capital=10000, transaction_cost=None, asset_type=None):
        self.initial_capital = initial_capital

        # Si se pasa asset_type, usar costo apropiado; si no, usar el dado o default
        if transaction_cost is not None:
            self.transaction_cost = transaction_cost
        elif asset_type and asset_type in self.DEFAULT_COSTS:
            self.transaction_cost = self.DEFAULT_COSTS[asset_type]
        else:
            self.transaction_cost = 0.0005  # Fallback conservador

        self.trades = []
        self.equity_curve = []
        self._total_costs = 0.0

    def run_backtest(self, df, prediction_col='Prediction', price_col='Close',
                     threshold=0.0, is_return=False):
        capital = self.initial_capital
        position = 0
        entry_price = 0
        entry_date = None
        signals = []
        self._total_costs = 0.0

        for i in range(len(df) - 1):
            current_price = df[price_col].iloc[i]
            predicted_val = df[prediction_col].iloc[i]
            next_price = df[price_col].iloc[i+1]
            date = df.index[i]
            signal = "HOLD"

            if is_return:
                if predicted_val > threshold:
                    new_position = 1
                elif predicted_val < -threshold:
                    new_position = -1
                else:
                    new_position = position
            else:
                if predicted_val > current_price * (1 + threshold):
                    new_position = 1
                elif predicted_val < current_price * (1 - threshold):
                    new_position = -1
                else:
                    new_position = position

            if new_position != position:
                if position != 0:
                    if position == 1:
                        pnl_pct = (current_price - entry_price) / entry_price
                    else:
                        pnl_pct = (entry_price - current_price) / entry_price
                    # Descontar costos de transacción (ida y vuelta)
                    cost = self.transaction_cost
                    pnl_pct -= cost
                    self._total_costs += cost * capital
                    capital *= (1 + pnl_pct)
                    self.trades.append({
                        'Entry Date': entry_date,
                        'Exit Date': date,
                        'Type': 'LONG' if position == 1 else 'SHORT',
                        'Entry Price': entry_price,
                        'Exit Price': current_price,
                        'PnL %': pnl_pct * 100,
                        'Cost %': cost * 100,
                        'Capital': capital
                    })
                position = new_position
                entry_price = current_price
                entry_date = date
                if position == 1:
                    signal = "BUY"
                elif position == -1:
                    signal = "SELL"

            signals.append({
                'Date': date,
                'Price': current_price,
                'Prediction': predicted_val,
                'Signal': signal,
                'Position': "LONG" if position == 1 else "SHORT" if position == -1 else "NEUTRAL"
            })
            self.equity_curve.append(capital)

        # Cerrar posición abierta al final
        if position != 0:
            last_price = df[price_col].iloc[-1]
            if position == 1:
                pnl_pct = (last_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - last_price) / entry_price
            cost = self.transaction_cost
            pnl_pct -= cost
            self._total_costs += cost * capital
            capital *= (1 + pnl_pct)
            self.trades.append({
                'Entry Date': entry_date,
                'Exit Date': df.index[-1],
                'Type': 'LONG' if position == 1 else 'SHORT',
                'Entry Price': entry_price,
                'Exit Price': last_price,
                'PnL %': pnl_pct * 100,
                'Cost %': cost * 100,
                'Capital': capital
            })

        results = pd.DataFrame(self.trades)
        signals_df = pd.DataFrame(signals)
        return results, signals_df, capital

    def get_metrics(self):
        if not self.trades:
            return {
                'Total Trades': 0,
                'Win Rate': 0.0,
                'Profit Factor': 0.0,
                'Total Return %': 0.0,
                'Max Drawdown %': 0.0,
                'Sharpe Ratio': 0.0,
                'Avg Win %': 0.0,
                'Avg Loss %': 0.0,
                'Best Trade %': 0.0,
                'Worst Trade %': 0.0,
                'Total Costs $': 0.0,
                'Cost per Trade $': 0.0
            }

        df = pd.DataFrame(self.trades)
        wins = df[df['PnL %'] > 0]
        losses = df[df['PnL %'] <= 0]

        win_rate = len(wins) / len(df) * 100
        gross_profit = wins['PnL %'].sum()
        gross_loss = abs(losses['PnL %'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss != 0 else float('inf')
        total_return = (self.equity_curve[-1] - self.initial_capital) / self.initial_capital * 100

        # Max Drawdown
        peak = self.initial_capital
        max_dd = 0
        for eq in self.equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd

        # Sharpe Ratio (anualizado, asumiendo daily returns)
        if len(self.equity_curve) > 1:
            eq_arr = np.array(self.equity_curve)
            returns = np.diff(eq_arr) / eq_arr[:-1]
            sharpe = (np.mean(returns) / np.std(returns) * np.sqrt(252)
                      if np.std(returns) > 0 else 0.0)
        else:
            sharpe = 0.0

        avg_win = wins['PnL %'].mean() if len(wins) > 0 else 0.0
        avg_loss = losses['PnL %'].mean() if len(losses) > 0 else 0.0

        return {
            'Total Trades': len(df),
            'Win Rate': round(win_rate, 1),
            'Profit Factor': round(profit_factor, 2),
            'Total Return %': round(total_return, 2),
            'Max Drawdown %': round(max_dd, 2),
            'Sharpe Ratio': round(sharpe, 2),
            'Avg Win %': round(avg_win, 2),
            'Avg Loss %': round(avg_loss, 2),
            'Best Trade %': round(df['PnL %'].max(), 2),
            'Worst Trade %': round(df['PnL %'].min(), 2),
            'Total Costs $': round(self._total_costs, 2),
            'Cost per Trade $': round(self._total_costs / len(df), 2) if len(df) > 0 else 0.0
        }