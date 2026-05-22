import sys
import os
import asyncio
from datetime import datetime, timedelta

# Setup path
sys.path.append(os.getcwd())

from src.services.crypto_manager import get_crypto_manager
from src.live.crypto_connector import get_crypto_connector

async def debug_bitmex_history():
    manager = get_crypto_manager()
    # Find BitMex account
    accounts = manager.get_accounts()
    bitmex_acc = next((a for a in accounts if a['broker'] == 'bitmex'), None)
    
    if not bitmex_acc:
        print("BitMex account not found in crypto_accounts.json")
        return

    acc_id = bitmex_acc['id']
    print(f"Testing history for {bitmex_acc['name']} (ID: {acc_id})")
    
    account = manager.get_account_full(acc_id)
    conn = get_crypto_connector(acc_id)
    
    if not conn.connected:
        print("Connecting...")
        conn.connect()
    
    print("Exchange connected. Loading markets...")
    conn.exchange.load_markets()
    
    since = int((datetime.now() - timedelta(days=7)).timestamp() * 1000)
    
    print(f"\n--- Method 1: fetch_my_trades(None, since={since}) ---")
    try:
        trades = conn.exchange.fetch_my_trades(None, since=since, limit=50)
        print(f"Found {len(trades)} trades")
        for t in trades[:5]:
            print(f"  {t['symbol']} | {t['side']} | {t['amount']} | {t['price']} | {t['datetime']}")
    except Exception as e:
        print(f"Failed: {e}")

    print(f"\n--- Method 2: fetch_ledger(None, since={since}) ---")
    try:
        ledger = conn.exchange.fetch_ledger(None, since=since, limit=50)
        print(f"Found {len(ledger)} ledger entries")
        for l in ledger[:5]:
            print(f"  {l['id']} | {l['type']} | {l['amount']} | {l['currency']} | {l['datetime']}")
    except Exception as e:
        print(f"Failed: {e}")

    print(f"\n--- Method 3: fetch_closed_orders(None, since={since}) ---")
    try:
        orders = conn.exchange.fetch_closed_orders(None, since=since, limit=50)
        print(f"Found {len(orders)} closed orders")
        for o in orders[:5]:
            print(f"  {o['symbol']} | {o['status']} | {o['amount']} | {o['price']} | {o['datetime']}")
    except Exception as e:
        print(f"Failed: {e}")

    # Check the actual connector method
    print("\n--- Method 4: Connector.get_deals() ---")
    try:
        deals = conn.get_deals(date_from=datetime.now() - timedelta(days=7))
        print(f"Connector found {len(deals)} deals")
        for d in deals[:5]:
            print(f"  {d['symbol']} | {d['type']} | {d['volume']} | {d['price_open']} | {d['time']}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(debug_bitmex_history())
