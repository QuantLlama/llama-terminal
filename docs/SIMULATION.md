# Simulation compatibility

Release-readiness T6 preserves interfaces and results (S1/S2/S5). These are
separate accounting modes, not interchangeable implementations. No live
connector or saved model is needed for the synthetic compatibility tests.

| Public facade | Preserved contract |
| --- | --- |
| `src.analysis.backtester.Backtester.run_backtest` | Prediction/price or predicted-return signals; round-trip percentage costs deducted on closing/reversal; compounded capital; final position liquidated. Returns `(trades DataFrame, signals DataFrame, capital)`. |
| `src.engine.backtesting.backtester.Backtester.run` | Strategy signals, risk-sized integer contracts, currency PnL = price difference / tick size × contracts × tick value; no transaction cost deduction and no terminal liquidation. Returns a metrics dictionary. |
| `src.engine.backtesting.metrics.calculate_trading_metrics` | Extended platform metrics, including currency PnL, percent total return, fractional win rate/drawdown, streaks and R multiples. Not the trainer schema. |
| `src.engine.core.risk_manager.RiskManager` | Balance-relative sizing/daily absolute-PnL threshold and consecutive-loss stopping; uses existing `utils.helpers` sizing/risk functions. |
| `src.services.order_gateway.risk_validator.RiskValidator` | Stateful live order validation: source-specific limits, positions, daily loss, rate/session checks. Validation does not record a fill/order; explicit methods update counters/positions. |

## Shared arithmetic, not shared accounting

`src/engine/risk_math.py::profit_factor` replaces the identical calculation in
both platform metrics consumers: absolute sum of winning PnLs / sum of losing
PnLs, or **0 when there are no losing trades**. Callers still classify strictly
positive/negative PnLs and retain their own empty-result schemas. Zero and NaN
PnLs enter neither group; infinity divided by infinity remains NaN. No input
validation, rounding, finite-value coercion or fee policy was added.

Trainer profit factor intentionally stays separate: no losses means infinity,
not zero. Trainer win rate/drawdown are percentages; platform uses fractions.
Trainer drawdown uses a running peak denominator, platform initial balance.
Trainer Sharpe uses NumPy population standard deviation; platform uses pandas
sample standard deviation. Combining these would silently change results.

## Characterized examples

`tests/test_simulation_compatibility.py` pins full public result schemas and
records with synthetic prices/signals and a fixed live-validation clock.
Engine risk configuration is synthetic (1% trade risk, 5% daily threshold,
maximum 3 contracts); no runtime configuration or `.env` is loaded. Imports
isolate package bootstrapping and logging, not the calculation implementations.

- Trainer prices `[100, 110, 99]`, predictions `[120, 90, 99]`, initial 10000,
  cost 0.01: closing capitals `10900.0`, `11881.0`, costs `209.0`, each trade
  PnL percent `9.000000000000002`. Equity stays `[10000, 10900.0]`: metrics
  report return `9.0`, not the final liquidated return. This existing behavior
  is preserved, not silently repaired. Repeated trainer runs also retain
  trade/equity lists; this slice does not redesign lifecycle/reset policy.
- Platform prices `[100, 101, 102]`, signals `[1, 0, 1]`, synthetic strategy:
  one closed 3-contract long earns `6.0`; terminal entry remains unliquidated.
  Equity `[10000, 10000, 10006.0, 10006.0]`, Sharpe `9.165151389911681`,
  profit factor `0`. Defaults remain tick size `0.25`, tick value `0.5`.
- Engine daily PnL `+500` at balance 10000 passes the synthetic 5% limit;
  `+500.01` stops trading. Live daily PnL `-500` rejects at the default
  $500 loss boundary. These are different signs/boundaries/policies, not
  equivalent validation primitives.

## Remaining work

This is one bounded arithmetic extraction, not closure of issues #4/#5.
The active legacy execution entry point is untouched. A compatible unified
architecture keeps the existing trainer/platform facades as explicit mode
adapters, shares only demonstrated identical arithmetic, and leaves live risk
state/policy separate from engine sizing. Further consolidation needs its own
public examples and differential evidence before moving any lifecycle,
liquidation, metric or risk policy. Suspected trainer terminal-metric/reset bugs
require a separately approved behavior change.

Focused verification:

```sh
venv_linux/bin/python -m pytest -q tests/test_simulation_compatibility.py
```
