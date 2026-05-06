
import MetaTrader5 as mt5
print(f"MetaTrader5 version: {getattr(mt5, '__version__', 'unknown')}")
print(f"Has copy_ticks_from_pos: {hasattr(mt5, 'copy_ticks_from_pos')}")
print(f"Has copy_ticks_from: {hasattr(mt5, 'copy_ticks_from')}")
print(f"Module members: {[m for m in dir(mt5) if not m.startswith('_')]}")
