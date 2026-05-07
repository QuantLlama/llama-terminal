
import sys
import os
print(f"sys.platform: {sys.platform}")
print(f"os.name: {os.name}")
print(f"USE_MT5_API env: {os.getenv('USE_MT5_API', 'not set')}")
