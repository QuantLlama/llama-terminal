import sys
import os
from datetime import datetime, timedelta

# Asegurar que el path del proyecto esté disponible
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.live.mt5_native_connector import get_mt5_connector

def test_deals():
    connector = get_mt5_connector()
    print("Conectando a MT5...")
    if not connector.connect():
        print("Error: No se pudo conectar a MT5")
        return
    
    print("Conectado con éxito.")
    # Obtener deals de los últimos 10 años (ALL)
    date_from = datetime.now() - timedelta(days=3650)
    deals = connector.get_deals(date_from=date_from)
    
    print(f"Total de deals recuperados: {len(deals)}")
    
    if len(deals) == 0:
        print("No se encontraron deals.")
        return
        
    # Ordenar por tiempo
    deals.sort(key=lambda x: x['time'])
    
    print("\nPrimeros 5 deals (más antiguos):")
    for d in deals[:5]:
        dt = datetime.fromtimestamp(d['time'])
        print(f"Ticket: {d['ticket']}, Time: {dt}, Symbol: {d['symbol']}, Type: {d['type']}, Profit: {d['profit']}, Comm: {d['commission']}, Swap: {d['swap']}")
        
    print("\nÚltimos 5 deals (más recientes):")
    for d in deals[-5:]:
        dt = datetime.fromtimestamp(d['time'])
        print(f"Ticket: {d['ticket']}, Time: {dt}, Symbol: {d['symbol']}, Type: {d['type']}, Profit: {d['profit']}, Comm: {d['commission']}, Swap: {d['swap']}")

    # Calcular PnL de trading y balance
    pnl_trading = 0
    pnl_total = 0
    dep_ret = 0
    
    for d in deals:
        if d['type'] in [0, 1]:  # BUY / SELL
            pnl_trading += (d['profit'] or 0) + (d['commission'] or 0) + (d['swap'] or 0)
        elif d['type'] == 2:  # BALANCE
            dep_ret += d['profit'] or 0
        pnl_total += (d['profit'] or 0) + (d['commission'] or 0) + (d['swap'] or 0)
            
    print("\n--- RESUMEN DE CÁLCULO ---")
    print(f"PnL Neto Trading (BUY/SELL con comisiones y swaps): {pnl_trading:.2f}")
    print(f"Total Depósitos/Retiros (BALANCE): {dep_ret:.2f}")
    print(f"Impacto Total en la Cuenta (Trading + Balance): {pnl_total:.2f}")
    
    acc_info = connector.get_account_info()
    if acc_info:
        print(f"Balance actual de la cuenta: {acc_info.get('balance', 0.0)}")
        print(f"Equidad actual de la cuenta: {acc_info.get('equity', 0.0)}")

if __name__ == '__main__':
    test_deals()
