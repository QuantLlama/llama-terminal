import sys, os, time, datetime
sys.path.insert(0, '/run/media/pabloezm/Respaldos/Pltaforma_Terminal_Llama')
from src.live.crypto_connector import get_connector
from src.services.crypto_manager import get_crypto_manager

manager = get_crypto_manager()
accounts = manager.get_accounts()
master_acc = next((acc for acc in accounts if acc.get("is_master")), None) or accounts[0]
conn = get_connector(master_acc["id"])
conn.connect()

income = conn.exchange.fapiPrivateGetIncome({'limit': 1000})
total = 0.0
for entry in income:
    val = float(entry.get('income', 0.0))
    t = entry.get('incomeType', '')
    if t in ('REALIZED_PNL', 'COMMISSION', 'FUNDING_FEE'):
        total += val

print(f"Total historical PNL: {total}")
