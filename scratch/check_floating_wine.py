import urllib.request
import json
import time

try:
    req = urllib.request.Request("http://127.0.0.1:8050/api/state")
    with urllib.request.urlopen(req) as response:
        # The /api/state endpoint returns JSON? No, it returned HTML before.
        pass
except Exception as e:
    print("Error:", e)

# Instead, read the logs or use python directly
