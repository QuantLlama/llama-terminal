import asyncio
import sys
import os

sys.path.insert(0, '/run/media/pabloezm/Respaldos/Pltaforma_Terminal_Llama')

from src.services.crypto_manager import get_crypto_manager
from src.live.crypto_connector import get_connector

async def main():
    manager = get_crypto_manager()
    account_id = list(manager.crypto_accounts.keys())[0] if manager.crypto_accounts else "test_binance"
    
    # We will get the connector directly to bypass any FastAPI dependencies
    acc = manager.crypto_accounts[account_id]
    connector = get_connector(
        account_id=acc['id'],
        exchange_id=acc['exchange'],
        api_key=acc['api_key'],
        api_secret=acc['api_secret'],
        passphrase=acc.get('passphrase'),
        test_mode=acc.get('is_testnet', True)
    )
    
    connector.connect()
    
    snapshot = connector.get_account_snapshot()
    all_pos = snapshot.get('positions', [])
    print(f"Total positions in snapshot: {len(all_pos)}")
    for p in all_pos:
        print(f"  Position symbol: {p['symbol']}, volume: {p['volume']}, ticket: {p.get('ticket')}")
        clean_p = p['symbol'].replace('/', '').replace(':', '').split('-')[0]
        print(f"  Clean symbol: {clean_p}")
        
    symbol = "BTCUSDT"
    target_symbol = connector._resolve_sym(symbol)
    print(f"\nResolved symbol for {symbol}: {target_symbol}")
    
    positions = connector.get_positions(target_symbol, force_fetch=True)
    print(f"Filtered positions for {target_symbol}: {len(positions)}")

asyncio.run(main())
