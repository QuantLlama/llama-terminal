import requests
import json

try:
    res = requests.get("http://127.0.0.1:8000/api/indicators/calculate?symbol=BTCUSD&timeframe=1m&limit=100&platform=crypto")
    data = res.json()
    if 'indicators' in data and 'liquidity_heatmap' in data['indicators']:
        hm = data['indicators']['liquidity_heatmap']
        print("Heatmap data found! Length:", len(hm.get('data', [])))
        if len(hm.get('data', [])) > 0:
            print("Sample:", hm['data'][0])
    else:
        print("No liquidity_heatmap in response. Keys:", data.get('indicators', {}).keys())
except Exception as e:
    print("Error:", e)
