import sys, os, time
from datetime import datetime

script_content = """
import sys
import os
import time
from datetime import datetime, timedelta
import MetaTrader5 as mt5

if not mt5.initialize():
    print("MT5 init failed")
    sys.exit(1)

local_now = datetime.now()
local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
print(f"Local midnight: {local_midnight}")

deals = mt5.history_deals_get(local_midnight, local_now + timedelta(days=1))
if deals:
    print(f"Deals found: {len(deals)}")
    daily_realized = 0.0
    for d in deals:
        if d.type in [0, 1]: # BUY or SELL
            p = getattr(d, 'profit', 0.0) or 0.0
            c = getattr(d, 'commission', 0.0) or 0.0
            s = getattr(d, 'swap', 0.0) or 0.0
            daily_realized += (p + c + s)
            print(f"Deal {d.ticket}: time={d.time} type={d.type} profit={p} comm={c} swap={s} symbol={d.symbol}")
    print(f"Daily realized: {daily_realized}")
else:
    print("No deals found")

mt5.shutdown()
"""
with open("scratch/check_mt5_deals_wine.py", "w") as f:
    f.write(script_content)

