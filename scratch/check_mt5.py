import MetaTrader5 as mt5
print(f"Has copy_ticks_from_pos: {hasattr(mt5, 'copy_ticks_from_pos')}")
print(f"MT5 Version: {mt5.__version__ if hasattr(mt5, '__version__') else 'unknown'}")
