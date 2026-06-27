import sys
import os
sys.path.append(os.getcwd())
import MetaTrader5 as mt5
from datetime import datetime
import time

def test():
    if not mt5.initialize():
        print("initialize() failed, error code =",mt5.last_error())
        return

    broker_now_ts = 0
    symbols = mt5.symbols_get()
    print(f"Got {len(symbols) if symbols else 0} symbols")
    if symbols:
        for s in symbols[:20]:
            tick = mt5.symbol_info_tick(s.name)
            if tick and tick.time > broker_now_ts:
                broker_now_ts = tick.time
                
    if broker_now_ts == 0:
        broker_now_dt = datetime.now()
    else:
        broker_now_dt = datetime.fromtimestamp(broker_now_ts)
        
    start_of_day_dt = broker_now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    today_ts = int(start_of_day_dt.timestamp())
    
    print(f"broker_now_ts: {broker_now_ts}")
    print(f"broker_now_dt: {broker_now_dt}")
    print(f"start_of_day_dt: {start_of_day_dt}")
    print(f"today_ts: {today_ts}")
    
    fetch_start = today_ts - 3600
    fetch_end = int(time.time()) + 7200
    
    print(f"fetch_start: {fetch_start} -> {datetime.fromtimestamp(fetch_start)}")
    print(f"fetch_end: {fetch_end} -> {datetime.fromtimestamp(fetch_end)}")
    
    mt5.history_deals_get(int(time.time()) - 86400, fetch_end)
    deals = mt5.history_deals_get(fetch_start, fetch_end)
    
    print(f"Deals found: {len(deals) if deals else 0}")
    
    daily_realized = 0.0
    if deals:
        for d in deals:
            if d.time >= today_ts:
                print(f"Deal inside today: {d.time} -> {datetime.fromtimestamp(d.time)}")
                if d.type in [mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL]:
                    p = getattr(d, 'profit', 0.0) or 0.0
                    c = getattr(d, 'commission', 0.0) or 0.0
                    s = getattr(d, 'swap', 0.0) or 0.0
                    daily_realized += (p + c + s)
                    
    print(f"Daily realized: {daily_realized}")
    mt5.shutdown()

test()
