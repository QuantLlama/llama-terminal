
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

if not mt5.initialize():
    print("Initialize failed")
    quit()

symbol = "MNQM26"
# Request 100 ticks to see more variety
ticks = mt5.copy_ticks_from(symbol, datetime.now() - timedelta(minutes=5), 100, mt5.COPY_TICKS_ALL)

if ticks is not None:
    df = pd.DataFrame(ticks)
    
    buys = df[df['flags'] & 32]
    sells = df[df['flags'] & 64]
    
    print(f"Total ticks: {len(df)}")
    print(f"Buys (flag 32): {len(buys)}")
    print(f"Sells (flag 64): {len(sells)}")
    
    if len(sells) > 0:
        print("\nFirst 5 Sells:")
        print(sells[['time_msc', 'last', 'bid', 'ask', 'volume', 'flags']].head())
    else:
        print("\nNO SELLS FOUND in 100 ticks!")
        print("Sample of flags seen:", df['flags'].unique())
else:
    print("No ticks found")

mt5.shutdown()
