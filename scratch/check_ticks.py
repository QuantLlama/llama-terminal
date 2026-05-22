import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta, timezone

if not mt5.initialize():
    print(f"initialize() failed, error code = {mt5.last_error()}")
    quit()

symbol = "MNQM26"
# Check if symbol exists
info = mt5.symbol_info(symbol)
if info is None:
    print(f"Symbol {symbol} not found")
    mt5.shutdown()
    quit()

print(f"Symbol {symbol} found. Path: {info.path}")

# Try to get ticks
ticks = mt5.copy_ticks_from_pos(symbol, 0, 10, mt5.COPY_TICKS_ALL)
if ticks is not None:
    print(f"Found {len(ticks)} ticks via copy_ticks_from_pos")
    print(pd.DataFrame(ticks).head())
else:
    print("copy_ticks_from_pos returned None")

# Try via time
from_dt = datetime.now(timezone.utc) - timedelta(hours=1)
ticks = mt5.copy_ticks_from(symbol, from_dt, 10, mt5.COPY_TICKS_ALL)
if ticks is not None:
    print(f"Found {len(ticks)} ticks via copy_ticks_from")
else:
    print("copy_ticks_from returned None")

mt5.shutdown()
