import asyncio
import sys
import os
sys.path.append(os.getcwd())
from src.services.crypto_manager import get_crypto_manager
from src.live.crypto_connector import get_connector
from datetime import datetime

async def main():
    manager = get_crypto_manager()
    master = manager.get_accounts()[0]
    conn = get_connector(master["id"])
    conn.connect()
    deals = conn.get_deals()
    
    # Let's get today's 00:00 UTC timestamp
    now = datetime.utcnow()
    start_time = datetime(now.year, now.month, now.day, 0, 0, 0).timestamp()
    
    total = 0
    count = 0
    for d in deals:
        if d['entry'] == 1 and d['time'] >= start_time:
            total += d['profit']
            total += d['commission']
            count += 1
            print(f"[{d['datetime']}] +{d['profit']} (fee: {d['commission']})")
    print(f"Total: {total} over {count} trades")
    
    start_time_yest = datetime(now.year, now.month, now.day-1, 0, 0, 0).timestamp()
    total_yest = 0
    for d in deals:
        if d['entry'] == 1 and d['time'] >= start_time_yest and d['time'] < start_time:
            total_yest += d['profit'] + d['commission']
    print(f"Total Yesterday: {total_yest}")
    
asyncio.run(main())
