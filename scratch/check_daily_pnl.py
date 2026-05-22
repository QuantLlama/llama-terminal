import sys, os, time
from datetime import datetime, timedelta
sys.path.insert(0, '/run/media/pabloezm/Respaldos/Pltaforma_Terminal_Llama')
from src.live.crypto_connector import get_connector
from src.services.crypto_manager import get_crypto_manager

manager = get_crypto_manager()
accounts = manager.get_accounts()
master_acc = next((acc for acc in accounts if acc.get("is_master")), None) or accounts[0]
conn = get_connector(master_acc["id"])
conn.connect()

now = datetime.utcnow()
session_start = datetime(now.year, now.month, now.day, 0, 0, 0)
deals = conn.get_deals(date_from=session_start)
realized = sum(float(d.get('profit', 0.0)) for d in deals)
print(f"Session start: {session_start}")
print(f"Realized: {realized}")
for d in deals:
    print(d)

