import sys, os
sys.path.insert(0, '/run/media/pabloezm/Respaldos/Pltaforma_Terminal_Llama')
from src.live.crypto_connector import get_connector
from src.services.crypto_manager import get_crypto_manager

manager = get_crypto_manager()
accounts = manager.get_accounts()
master_acc = next((acc for acc in accounts if acc.get("is_master")), None) or accounts[0]
conn = get_connector(master_acc["id"])

print("CONNECTING...")
conn.connect()
print("POSITIONS:")
pos = conn.exchange.fetch_positions()
import pprint
for p in pos:
    if float(p.get('contracts', 0) or p.get('positionAmt', 0) or 0) != 0:
        pprint.pprint(p)
