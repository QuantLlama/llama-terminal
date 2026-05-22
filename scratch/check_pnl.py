import urllib.request, json
try:
    resp = urllib.request.urlopen("http://localhost:5000/api/realtime_batch?symbols=BTCUSDT&platform=crypto")
    data = json.loads(resp.read())
    print("PORT 5000 SUCCESS:")
    print("daily_pnl:", data.get('account', {}).get('daily_pnl'))
    print("profit:", data.get('account', {}).get('profit'))
except Exception as e:
    print("PORT 5000 FAIL:", e)

try:
    resp = urllib.request.urlopen("http://localhost:8000/api/realtime_batch?symbols=BTCUSDT&platform=crypto")
    data = json.loads(resp.read())
    print("PORT 8000 SUCCESS:")
    print("daily_pnl:", data.get('account', {}).get('daily_pnl'))
    print("profit:", data.get('account', {}).get('profit'))
except Exception as e:
    print("PORT 8000 FAIL:", e)
