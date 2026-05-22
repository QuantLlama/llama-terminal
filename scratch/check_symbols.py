
import asyncio
import sys
import os

# Añadir el path del proyecto para importar los módulos
sys.path.append(os.getcwd())

from src.live.connector import get_mt5_connector

async def main():
    connector = get_mt5_connector()
    print("Intentando conectar a MT5...")
    if not connector.connect():
        print("Error: No se pudo conectar a MT5.")
        return

    print("Conexión exitosa.")
    symbols = connector.get_available_symbols()
    print(f"Símbolos disponibles ({len(symbols)}):")
    
    # Mostrar los primeros 20 y los que contengan 'NQ' o 'ES'
    count = 0
    for s in symbols:
        name = s['symbol']
        if count < 20 or 'NQ' in name or 'ES' in name:
            print(f" - {name} ({s['description']})")
        count += 1
    
    if count > 20:
        print(f"... y {count - 20} más.")

    # Verificar el estado de los símbolos específicos reportados en logs
    for sym in ["MNQM26", "MESM26", "MNQM24", "MESM24"]:
        info = connector.symbol_info(sym)
        if info:
            print(f"INFO {sym}: Visible={info.visible}, Select={info.select}")
        else:
            print(f"INFO {sym}: No encontrado.")

if __name__ == "__main__":
    asyncio.run(main())
