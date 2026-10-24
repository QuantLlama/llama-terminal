"""Synthetic public-facade contracts; no runtime config, logs or connectors."""
import importlib
import importlib.util
import logging
import math
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_facades(root, monkeypatch):
    # Private import namespace prevents package __init__ side effects (.env/logs).
    def package(name, relative):
        module = ModuleType(name)
        module.__path__ = [str(root / relative)]
        monkeypatch.setitem(sys.modules, name, module)
        return module

    def load(name, relative):
        spec = importlib.util.spec_from_file_location(name, root / relative)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        return module

    package('_compat', 'src')
    package('_compat.engine', 'src/engine')
    package('_compat.engine.core', 'src/engine/core')
    package('_compat.engine.backtesting', 'src/engine/backtesting')
    utils = package('_compat.engine.utils', 'src/engine/utils')
    logger = ModuleType('_compat.engine.utils.logger')
    logger.setup_logger = lambda name: logging.getLogger('compat.' + name)
    monkeypatch.setitem(sys.modules, logger.__name__, logger)
    helpers = load('_compat.engine.utils.helpers', 'src/engine/utils/helpers.py')
    utils.calculate_contracts = helpers.calculate_contracts
    utils.calculate_position_risk = helpers.calculate_position_risk
    utils.CONFIG = {'RISK': {'MAX_DAILY_DRAWDOWN_PCT': 0.05,
                            'MAX_TRADE_RISK_PCT': 0.01,
                            'MAX_CONCURRENT_TRADES': 3}}
    package('_compat.gateway', 'src/services/order_gateway')
    models = load('_compat.gateway.models', 'src/services/order_gateway/models.py')
    risk = load('_compat.gateway.risk_validator', 'src/services/order_gateway/risk_validator.py')

    class FixedDate(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 14, 12, tzinfo=tz)

    monkeypatch.setattr(risk, 'datetime', FixedDate)
    monkeypatch.setattr(risk, 'time', SimpleNamespace(time=lambda: 1768392000.0))
    return SimpleNamespace(
        trainer=load('_compat.trainer', 'src/analysis/backtester.py').Backtester,
        platform=load('_compat.engine.backtesting.backtester', 'src/engine/backtesting/backtester.py').Backtester,
        metrics=load('_compat.engine.backtesting.metrics', 'src/engine/backtesting/metrics.py'),
        manager=load('_compat.engine.core.risk_manager', 'src/engine/core/risk_manager.py').RiskManager,
        validator=risk.RiskValidator, models=models,
    )


@pytest.fixture
def facades(monkeypatch):
    before = set(sys.modules)
    try:
        yield load_facades(ROOT, monkeypatch)
    finally:
        for name in set(sys.modules) - before:
            if name.startswith('_compat.'):
                sys.modules.pop(name, None)


class SyntheticStrategy:
    def __init__(self, params):
        self.params = params or {}

    def generate_signals(self, data):
        return data

    def check_entry_conditions(self, conditions, signal):
        return True

    def calculate_exit_levels(self, price, direction, atr):
        return {'stop_loss': price - 1, 'take_profit': price + 1}

    def should_exit(self, price, position):
        return 'SYNTHETIC_EXIT' if price != position['entry_price'] else None


def public_examples(f):
    trainer = f.trainer(transaction_cost=0.01)
    trades, signals, capital = trainer.run_backtest(pd.DataFrame(
        {'Close': [100.0, 110.0, 99.0], 'Prediction': [120.0, 90.0, 99.0]}))
    platform = f.platform(pd.DataFrame({'close': [100.0, 101.0, 102.0],
                                       'signal': [1, 0, 1]}),
                          strategy_class=SyntheticStrategy)
    platform_metrics = platform.run()
    detailed = f.metrics.calculate_trading_metrics(platform.trades, platform.equity_curve, 10000)
    manager = f.manager(10000)
    sizes = [manager.calculate_position_size(100, 99), manager.check_trade_risk(100, 0)]
    manager.update_pnl(500)
    boundary = manager.check_daily_limits()
    manager.update_pnl(0.01)
    stopped = manager.should_stop_trading()
    validator = f.validator()
    order = f.models.OrderRequest('BTCUSD', f.models.OrderSide.BUY, 1,
                                  client_order_id='synthetic', timestamp=1768392000.0)
    valid = validator.validate(order).to_dict()
    validator.record_order(order)
    validator.update_position('BTCUSD', 10)
    before = validator.get_stats()
    rejected = validator.validate(order).to_dict()
    assert validator.get_stats() == before
    validator.update_pnl(-500)
    loss = validator.validate(order).to_dict()
    return {'trainer': (trades.to_dict('records'), signals.to_dict('records'), capital,
                        trainer.equity_curve, trainer.get_metrics()),
            'platform': (platform.trades, platform.equity_curve, platform_metrics, detailed),
            'manager': (sizes, boundary, stopped),
            'validator': (valid, rejected, loss, validator.get_stats())}


def test_public_accounting_and_risk_contracts(facades):
    result = public_examples(facades)
    trades, signals, capital, equity, metrics = result['trainer']
    assert trades == [
        {'Entry Date': 0, 'Exit Date': 1, 'Type': 'LONG', 'Entry Price': 100.0,
         'Exit Price': 110.0, 'PnL %': 9.000000000000002, 'Cost %': 1.0, 'Capital': 10900.0},
        {'Entry Date': 1, 'Exit Date': 2, 'Type': 'SHORT', 'Entry Price': 110.0,
         'Exit Price': 99.0, 'PnL %': 9.000000000000002, 'Cost %': 1.0, 'Capital': 11881.0}]
    assert signals == [
        {'Date': 0, 'Price': 100.0, 'Prediction': 120.0, 'Signal': 'BUY', 'Position': 'LONG'},
        {'Date': 1, 'Price': 110.0, 'Prediction': 90.0, 'Signal': 'SELL', 'Position': 'SHORT'}]
    assert capital == 11881.0
    assert equity == [10000, 10900.0]  # Terminal liquidation is NOT appended.
    assert metrics == {'Total Trades': 2, 'Win Rate': 100.0, 'Profit Factor': math.inf,
                       'Total Return %': 9.0, 'Max Drawdown %': 0, 'Sharpe Ratio': 0.0,
                       'Avg Win %': 9.0, 'Avg Loss %': 0.0, 'Best Trade %': 9.0,
                       'Worst Trade %': 9.0, 'Total Costs $': 209.0, 'Cost per Trade $': 104.5}
    trades, equity, metrics, detailed = result['platform']
    assert trades == [{'direction': 'LONG', 'entry_price': 100.0, 'entry_time': 0,
                       'exit_price': 101.0, 'exit_time': 1, 'contracts': 3,
                       'pnl': 6.0, 'exit_reason': 'SYNTHETIC_EXIT'}]
    assert equity == [10000, 10000, 10006.0, 10006.0]  # Final entry is not liquidated.
    assert metrics == {'total_trades': 1, 'total_pnl': 6.0, 'win_rate': 1.0,
                       'sharpe_ratio': 9.165151389911681, 'max_drawdown': 0.0,
                       'profit_factor': 0, 'avg_win': 6.0, 'avg_loss': 0}
    assert detailed == dict(metrics, total_pnl_pct=0.06, calmar_ratio=0,
                            max_consecutive_wins=1, max_consecutive_losses=0, avg_r_multiple=0)
    assert result['manager'] == ([3, False], True, True)
    valid, rejected, loss, stats = result['validator']
    base = {'is_valid': True, 'rejection_reason': None, 'message': 'Orden válida',
            'warnings': [], 'adjusted_quantity': None, 'adjusted_price': None, 'current_session': None}
    assert valid == base
    assert rejected == dict(base, is_valid=False, rejection_reason='MAX_POSITION_SIZE_EXCEEDED',
                            message='Posición resultante excede límite (11.00 > 10.0)')
    assert loss == dict(base, is_valid=False, rejection_reason='MAX_DAILY_LOSS_EXCEEDED',
                        message='Límite de pérdida diaria alcanzado ($500.00)')
    assert stats == {'current_date': '2026-01-14', 'daily_orders': 1, 'daily_algo_orders': 0,
                     'daily_manual_orders': 1, 'daily_pnl': -500.0, 'positions': {'BTCUSD': 10},
                     'limits': facades.models.RiskLimits().to_dict()}


@pytest.mark.parametrize('pnls,expected', [([], 0), ([0.0], 0), ([2.0], 0),
    ([-2.0], 0.0), ([3.0, -2.0, 0.0], 1.5), ([math.nan], 0),
    ([math.inf, -2.0], math.inf), ([math.inf, -math.inf], math.nan)])
def test_platform_profit_factor_modes(facades, pnls, expected):
    trades = [{'pnl': pnl} for pnl in pnls]
    platform = facades.platform(pd.DataFrame())
    platform.trades = trades
    platform.equity_curve = [10000, 10001, 10000]
    for metrics in (platform.calculate_metrics(),
                    facades.metrics.calculate_trading_metrics(trades, platform.equity_curve, 10000)):
        if math.isnan(expected):
            assert math.isnan(metrics['profit_factor'])
        else:
            assert metrics['profit_factor'] == expected


def test_shared_platform_profit_factor_policy_exists(facades):
    # This extraction has two real consumers; trainer's no-loss policy differs.
    shared = importlib.import_module('_compat.engine.risk_math')
    assert shared.profit_factor([3.0], [-2.0]) == 1.5
    assert shared.profit_factor([3.0], []) == 0
    assert shared.profit_factor([], [-2.0]) == 0.0
    assert math.isnan(shared.profit_factor([math.inf], [-math.inf]))
    assert facades.platform.calculate_metrics.__globals__['profit_factor'] is shared.profit_factor
    assert facades.metrics.profit_factor is shared.profit_factor


def test_defaults_empty_results_and_return_predictions(facades):
    trainer = facades.trainer()
    assert trainer.transaction_cost == 0.0005
    assert facades.trainer(asset_type='Crypto').transaction_cost == 0.002
    assert facades.trainer(transaction_cost=0, asset_type='Crypto').transaction_cost == 0
    assert trainer.get_metrics() == dict.fromkeys([
        'Total Trades', 'Win Rate', 'Profit Factor', 'Total Return %', 'Max Drawdown %',
        'Sharpe Ratio', 'Avg Win %', 'Avg Loss %', 'Best Trade %', 'Worst Trade %',
        'Total Costs $', 'Cost per Trade $'], 0.0)
    trades, signals, capital = trainer.run_backtest(pd.DataFrame(
        {'Close': [100.0, 110.0], 'Prediction': [0.1, 0.0]}), is_return=True)
    assert capital == 10995.0
    assert trades['Cost %'].tolist() == [0.05]
    assert signals['Signal'].tolist() == ['BUY']
    platform = facades.platform(pd.DataFrame({'close': [100.0], 'signal': [0]}),
                                strategy_class=SyntheticStrategy)
    assert platform.run() == dict.fromkeys(['total_trades', 'total_pnl', 'win_rate',
                                            'sharpe_ratio', 'max_drawdown', 'profit_factor'], 0)
    assert platform.tick_size == 0.25 and platform.tick_value == 0.5
    assert facades.metrics.calculate_trading_metrics([], [], 10000) == facades.metrics.get_empty_metrics()
