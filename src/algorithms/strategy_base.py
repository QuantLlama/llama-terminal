"""
QUANTUM LLAMA - Strategy Base Protocol
=======================================
Every trading strategy (current or custom) that wants to be compatible with
the platform backtesting and optimization engine MUST follow this contract.

MINIMUM REQUIREMENT
-------------------
Your class must have an `update(df)` method that:
  - Receives a pandas DataFrame with OHLCV data (and pre-calculated indicators)
  - Returns a tuple: (signal: str, metadata: dict)
    - signal  → one of: 'BUY', 'SELL', 'HOLD'
    - metadata → arbitrary dict with optional keys:
        'stop_loss'      → float price level for stop loss
        'take_profit'    → float price level for take profit
        'stop_loss_price'  (alias)
        'take_profit_price' (alias)

COLUMNS GUARANTEED BY THE ADAPTER
----------------------------------
The `PlatformStrategyAdapter` always pre-calculates and injects these columns
into the DataFrame before calling your strategy, so you can use them for free:
  - Open, High, Low, Close, Volume (both capitalized and lowercase)
  - direction   → +1 (bullish bar), -1 (bearish bar), 0 (doji)
  - last        → alias for Close
  - ATR         → Average True Range (14-period)
  - RSI         → Relative Strength Index (14-period)
  - EMA_Fast    → Exponential Moving Average (8-period)
  - EMA_Slow    → Exponential Moving Average (21-period)

EXAMPLE MINIMAL STRATEGY
-------------------------

    class MyStrategy:
        def __init__(self, config=None):
            config = config or {}
            self.threshold = config.get('threshold', 0.5)

        def update(self, df):
            # df has all guaranteed columns above
            if df['RSI'].iloc[-1] < 30:
                return 'BUY', {'reason': 'Oversold'}
            elif df['RSI'].iloc[-1] > 70:
                return 'SELL', {'reason': 'Overbought'}
            return 'HOLD', {}

REGISTERING YOUR STRATEGY
--------------------------
Add your strategy to `src/algorithms/__init__.py` in the CORE_ALGORITHMS dict
or simply place the .py file in the `src/algorithms/` folder — it will be
auto-discovered by the platform at runtime.

OPTIONAL BASE CLASS
-------------------
You may inherit from StrategyBase for IDE autocompletion and type hints.
It is NOT required. The system uses duck-typing: any class with update() works.
"""

from abc import ABC, abstractmethod
import pandas as pd
from typing import Tuple, Dict, Any


class StrategyBase(ABC):
    """
    Optional abstract base class for trading strategies.
    Inherit from this to get IDE support and enforce the contract.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize strategy with optional configuration dictionary.

        Args:
            config: Dictionary of strategy parameters. Keys and defaults
                    should be documented in CORE_ALGORITHMS config_schema.
        """
        self.config = config or {}

    @abstractmethod
    def update(self, df: pd.DataFrame) -> Tuple[str, Dict[str, Any]]:
        """
        Process a new bar and return a trading signal.

        The adapter calls this once per bar during backtesting with a sliding
        window of up to 1500 bars of history (or all available bars if fewer).

        Args:
            df: DataFrame with OHLCV + pre-computed indicators (see module docstring).
                Index is a DatetimeIndex.

        Returns:
            Tuple of:
                signal (str): 'BUY', 'SELL', or 'HOLD'
                metadata (dict): Optional context. Recognized keys:
                    - 'stop_loss' or 'stop_loss_price': float
                    - 'take_profit' or 'take_profit_price': float
        """
        ...
