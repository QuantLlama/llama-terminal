import MetaTrader5 as mt5
from datetime import datetime, timezone
import pandas as pd

def debug_mt5():
    if not mt5.initialize():
        print("Failed to initialize MT5")
        return

    symbol = "EURUSD"
    tf = mt5.TIMEFRAME_M1
    limit = 2
    
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, limit)
    if rates is None or len(rates) == 0:
        print("No rates found")
        return
        
    df_rates = pd.DataFrame(rates)
    print("Rates Sample:")
    print(df_rates[['time', 'open', 'close', 'tick_volume']])
    
    first_ts = int(df_rates['time'].iloc[0])
    last_ts = int(df_rates['time'].iloc[-1])
    
    print(f"\nFetching ticks from {datetime.fromtimestamp(first_ts)} to {datetime.now()}")
    
    ticks = mt5.copy_ticks_range(symbol, 
                                 datetime.fromtimestamp(first_ts, tz=timezone.utc), 
                                 datetime.now(tz=timezone.utc), 
                                 mt5.COPY_TICKS_ALL)
                                 
    if ticks is None or len(ticks) == 0:
        print("No ticks found in range")
        # Try without TZ
        print("Retrying without TZ...")
        ticks = mt5.copy_ticks_range(symbol, 
                                     datetime.fromtimestamp(first_ts), 
                                     datetime.now(), 
                                     mt5.COPY_TICKS_ALL)
        if ticks is not None:
             print(f"Found {len(ticks)} ticks without TZ")
    else:
        print(f"Found {len(ticks)} ticks with TZ")
        
    if ticks is not None and len(ticks) > 0:
        ticks_df = pd.DataFrame(ticks)
        print("\nTicks Sample (first 5):")
        print(ticks_df[['time', 'last', 'bid', 'ask', 'volume', 'flags']].head())
        
        # Check time alignment
        ticks_df['candle_time'] = (ticks_df['time'] // 60) * 60
        match = ticks_df[ticks_df['candle_time'] == first_ts]
        print(f"\nTicks matching first candle ({first_ts}): {len(match)}")
        
    mt5.shutdown()

if __name__ == "__main__":
    debug_mt5()
