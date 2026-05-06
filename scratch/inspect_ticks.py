
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

if not mt5.initialize():
    print("Initialize failed")
    quit()

symbol = "MNQM26" # Using the symbol from the logs
ticks = mt5.copy_ticks_from(symbol, datetime.now() - timedelta(minutes=5), 10, mt5.COPY_TICKS_ALL)

if ticks is not None:
    df = pd.DataFrame(ticks)
    print("Columns:", df.columns.tolist())
    print("Last 10 ticks data:")
    # Show last, bid, ask, flags and volume
    cols = ['time_msc', 'last', 'bid', 'ask', 'volume', 'flags']
    available_cols = [c for c in cols if c in df.columns]
    print(df[available_cols])
    
    # Check flags
    for i, row in df.iterrows():
        flags = int(row['flags'])
        buy = bool(flags & 32)
        sell = bool(flags & 64)
        print(f"Tick {i}: flags={flags}, BUY={buy}, SELL={sell}, last={row.get('last')}, bid={row.get('bid')}, ask={row.get('ask')}")
else:
    print("No ticks found")

mt5.shutdown()
