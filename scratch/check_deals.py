import asyncio
import sys
import os
sys.path.append(os.getcwd())
from src.services.crypto_manager import get_crypto_manager
from src.live.crypto_connector import get_connector

async def main():
    manager = get_crypto_manager()
    accounts = manager.get_accounts()
    master = next((acc for acc in accounts if acc.get("is_master")), accounts[0] if accounts else None)
    if not master:
        print("No master account")
        return
    conn = get_connector(master["id"])
    conn.connect()
    deals = conn.get_deals()
    for d in deals[:10]:
        if d['entry'] == 1:
            print(f"Time: {d['time']}, Profit: {d['profit']}, Comm: {d['commission']}, Comment: {d['comment']}")

asyncio.run(main())
