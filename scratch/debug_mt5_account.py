import sys, time, json
from datetime import datetime

script = """
import sys
import MetaTrader5 as mt5
import json

if not mt5.initialize():
    print(json.dumps({"error": "init failed"}))
    sys.exit(1)

acc = mt5.account_info()
if acc is None:
    print(json.dumps({"error": "no account info"}))
    sys.exit(1)

positions = mt5.positions_get()
deals = mt5.history_deals_get(0, 9999999999)

out = {
    "balance": acc.balance,
    "equity": acc.equity,
    "profit": acc.profit,
    "margin": acc.margin,
    "positions": len(positions) if positions else 0,
    "pos_profit": sum(p.profit for p in positions) if positions else 0,
    "deals_total": len(deals) if deals else 0
}
print("===JSON_START===")
print(json.dumps(out))
print("===JSON_END===")

from datetime import datetime, timedelta
local_midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
deals_today = mt5.history_deals_get(local_midnight, datetime.now() + timedelta(days=1))
realized_today = 0.0
if deals_today:
    for d in deals_today:
        if d.type in [0, 1]:
            realized_today += (getattr(d, 'profit', 0) or 0) + (getattr(d, 'commission', 0) or 0) + (getattr(d, 'swap', 0) or 0)
print(f"DEBUG Realized local_midnight: {realized_today}")

mt5.shutdown()
"""
with open("scratch/run_wine_mt5.py", "w") as f:
    f.write(script)
