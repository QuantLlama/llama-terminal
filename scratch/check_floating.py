import urllib.request
import json

try:
    req = urllib.request.Request("http://127.0.0.1:8000/api/account")
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        print("API 8000 PNL:", data.get('account', {}).get('daily_pnl'))
        print("API 8000 Profit:", data.get('account', {}).get('profit'))
except Exception as e:
    print("Error 8000:", e)
