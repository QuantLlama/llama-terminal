
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

if not mt5.initialize():
    print("Initialize failed")
    quit()

symbol = "MNQM26"
ticks = mt5.copy_ticks_from(symbol, datetime.now() - timedelta(minutes=5), 100, mt5.COPY_TICKS_ALL)

if ticks is not None:
    df = pd.DataFrame(ticks)
    
    df['is_buy_flag'] = (df['flags'] & 32) != 0
    df['is_sell_flag'] = (df['flags'] & 64) != 0
    
    # Inferred side
    df['inferred_side'] = 'NONE'
    # Use bitwise for mask
    last_val = df['last']
    ask_val = df['ask']
    bid_val = df['bid']
    vol_val = df['volume']
    
    # Only for ticks with volume
    mask_vol = vol_val > 0
    df.loc[mask_vol & (last_val >= ask_val), 'inferred_side'] = 'BUY'
    df.loc[mask_vol & (last_val <= bid_val), 'inferred_side'] = 'SELL'
    
    print(f"Total ticks: {len(df)}")
    print(f"Buys (flag 32): {df['is_buy_flag'].sum()}")
    print(f"Sells (flag 64): {df['is_sell_flag'].sum()}")
    print(f"Inferred BUY: {(df['inferred_side'] == 'BUY').sum()}")
    print(f"Inferred SELL: {(df['inferred_side'] == 'SELL').sum()}")
    
    print("\nSample of Sells (Flag or Inferred):")
    sells = df[(df['is_sell_flag']) | (df['inferred_side'] == 'SELL')]
    if not sells.empty:
        print(sells[['time_msc', 'last', 'bid', 'ask', 'volume', 'flags', 'is_buy_flag', 'is_sell_flag', 'inferred_side']].head(10))
    else:
        print("STILL NO SELLS FOUND!")
        print("\nAll trades with volume:")
        trades = df[df['volume'] > 0]
        print(trades[['time_msc', 'last', 'bid', 'ask', 'volume', 'flags', 'inferred_side']].head(10))
else:
    print("No ticks found")

mt5.shutdown()
