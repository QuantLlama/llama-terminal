import sys, os, time
from datetime import datetime
import urllib.request
import json

req = urllib.request.Request("http://127.0.0.1:8050/api/state")
try:
    with urllib.request.urlopen(req) as res:
        data = json.loads(res.read().decode())
        print(f"Daily PNL: {data.get('account', {}).get('daily_pnl')}")
        print(f"Profit: {data.get('account', {}).get('profit')}")
        print(f"Realized Today: {data.get('account', {}).get('realized_today')}")
except Exception as e:
    print(e)
