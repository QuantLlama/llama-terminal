import urllib.request, json
try:
    req = urllib.request.Request("http://127.0.0.1:8000/api/deals?platform=crypto", headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read())
    deals = data.get('deals', [])
    profit = sum(d.get('profit', 0.0) for d in deals)
    print("TOTAL PROFIT FROM /api/deals:", profit)
except Exception as e:
    print("PORT 8000 failed:", e)

try:
    # Need to check the actual port uvicorn is running on.
    import os, subprocess
    out = subprocess.check_output("ss -tlnp | grep python", shell=True, text=True)
    print("Ports:", out)
except Exception as e:
    pass
