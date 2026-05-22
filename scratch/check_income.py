import sys, os, time, datetime
sys.path.insert(0, '/run/media/pabloezm/Respaldos/Pltaforma_Terminal_Llama')
from src.live.crypto_connector import get_connector
from src.services.crypto_manager import get_crypto_manager

manager = get_crypto_manager()
accounts = manager.get_accounts()
master_acc = next((acc for acc in accounts if acc.get("is_master")), None) or accounts[0]
conn = get_connector(master_acc["id"])

print("CONNECTING...")
conn.connect()
print("GET DEALS (last 24h):")
from datetime import timedelta
date_from = datetime.datetime.now() - timedelta(days=1)
since = int(date_from.timestamp() * 1000)

income = conn.exchange.fapiPrivateGetIncome({'startTime': since, 'limit': 1000})

realized = 0.0
commission = 0.0
funding = 0.0

for entry in income:
    t = entry.get('incomeType', '')
    val = float(entry.get('income', 0.0))
    if t == 'REALIZED_PNL': realized += val
    elif t == 'COMMISSION': commission += val
    elif t == 'FUNDING_FEE': funding += val

print(f"Since: {date_from}")
print(f"Total entries: {len(income)}")
print(f"Realized PNL: {realized}")
print(f"Commission: {commission}")
print(f"Funding: {funding}")
print(f"TOTAL: {realized + commission + funding}")
