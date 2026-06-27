import sys
import os
import time
from datetime import datetime

script_content = """
import sys
import os
import time
from datetime import datetime
import MetaTrader5 as mt5

if not mt5.initialize():
    print("MT5 init failed")
    sys.exit(1)

positions = mt5.positions_get()
floating = 0.0
if positions:
    for p in positions:
        floating += p.profit
        
print(f"Floating profit: {floating}")
deals = mt5.history_deals_get(datetime.now().replace(hour=0,minute=0,second=0,microsecond=0), datetime.now() + time.timedelta(days=1)) if 'timedelta' not in sys.modules else mt5.history_deals_get(datetime.now().replace(hour=0,minute=0,second=0,microsecond=0), datetime.now())
# Wait, timedelta is not imported correctly in the above line, let's fix
"""
