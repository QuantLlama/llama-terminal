import urllib.request
import json

try:
    req = urllib.request.Request("http://127.0.0.1:8000/api/daily_pnl")
    with urllib.request.urlopen(req) as response:
        print("Response from daily_pnl:", response.read().decode())
except Exception as e:
    print("Error 8000:", e)

try:
    req = urllib.request.Request("http://127.0.0.1:5000/api/daily_pnl")
    with urllib.request.urlopen(req) as response:
        print("Response from daily_pnl 5000:", response.read().decode())
except Exception as e:
    print("Error 5000:", e)
