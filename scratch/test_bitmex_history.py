import sys
import os
import asyncio

# Setup path
sys.path.append(os.getcwd())

from src.services.crypto_manager import get_crypto_manager
from src.live.crypto_connector import get_crypto_connector

async def test_bitmex_history():
    manager = get_crypto_manager()
    acc_id = "590fa420" # BitMex
    account = manager.get_account_full(acc_id)
    
    if not account:
        print("Account not found")
        return

    print(f"Testing history for {account['name']} ({account['broker']})")
    
    conn = get_crypto_connector(acc_id)
    if not conn.connected:
        conn.connect()
    
    print("Exchange connected. Loading markets...")
    conn.exchange.load_markets()
    
    # Test 1: fetch_my_trades(None)
    print("\nTest 1: fetch_my_trades(None)")
    try:
        trades = conn.exchange.fetch_my_trades(None, limit=50)
        print(f"Result: Found {len(trades)} trades")
        if trades:
            print(f"First trade: {trades[0]['symbol']} at {trades[0]['datetime']}")
    except Exception as e:
        print(f"Failed: {e}")

    # Test 2: fetch_my_trades('XBTUSD')
    print("\nTest 2: fetch_my_trades('XBTUSD')")
    try:
        trades = conn.exchange.fetch_my_trades('XBTUSD', limit=50)
        print(f"Result: Found {len(trades)} trades")
        if trades:
            for t in trades[:5]:
                print(f"- {t['symbol']} | {t['side']} | {t['amount']} | {t['price']} | {t['datetime']}")
                # Check info for PNL
                info = t.get('info', {})
                print(f"  Info fields: {list(info.keys())}")
                for pnl_f in ['realisedPnl', 'realizedPnl', 'execComm']:
                    if pnl_f in info: print(f"  {pnl_f}: {info[pnl_f]}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_bitmex_history())
