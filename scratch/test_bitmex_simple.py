import ccxt
import json
import time
from datetime import datetime, timedelta

def test_bitmex():
    # Load keys
    try:
        with open('src/config/crypto_accounts.json', 'r') as f:
            accounts = json.load(f)
            # Find bitmex
            bitmex_data = next((a for a in accounts.values() if a['broker'] == 'bitmex'), None)
            if not bitmex_data:
                print("No bitmex account found")
                return
            
            # Note: Secrets are encrypted, but for this test I'll assume they might be raw if not using manager
            # Wait, I can't decrypt them without the key.
            # I'll use the BINANCE one as a baseline if bitmex fails
            print(f"Testing BitMex with API Key: {bitmex_data['api_key']}")
            
            # Since I can't decrypt here easily without the manager, 
            # I will just check what's available in the connector if I run it from inside the app.
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("This script needs to run in the app environment to decrypt keys.")
    print("I will modify the connector to log the results of fetch_my_trades(None) to the log file.")
