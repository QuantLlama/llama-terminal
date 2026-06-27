import os
import sys
import logging

# Añadir el path del proyecto al sys.path para poder importar src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.live.crypto_connector import get_connector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SignTradFi")

def sign_agreement():
    account_id = "271c6a5e" # ID de la cuenta BINANCE en crypto_accounts.json
    logger.info(f"Intentando obtener conector para la cuenta {account_id}...")
    
    connector = get_connector(account_id)
    if not connector:
        logger.error("No se pudo obtener el conector de Binance. Verifica las credenciales.")
        return
        
    logger.info("Conector obtenido con éxito. Intentando firmar el contrato TradFi-Perps...")
    
    # En CCXT, los endpoints de fapi se mapean dinámicamente.
    # El endpoint es POST /fapi/v1/stock/contract
    # CCXT mapea esto a fapiPrivatePostStockContract o fapiPrivatePostStockContract()
    try:
        if hasattr(connector.exchange, 'fapiPrivatePostStockContract'):
            # Probamos el método mapeado dinámicamente
            res = connector.exchange.fapiPrivatePostStockContract()
            logger.info(f"Respuesta de Binance: {res}")
        else:
            # Fallback usando request directo de CCXT
            # request (path, api='public', method='GET', params={}, headers=None, body=None)
            res = connector.exchange.request('stock/contract', 'fapiPrivate', 'POST')
            logger.info(f"Respuesta de Binance (vía request): {res}")
        logger.info("¡Contrato firmado con éxito a través de la API!")
    except Exception as e:
        logger.error(f"Error al intentar firmar el contrato: {e}")
        logger.info("Nota: Si esto falla, puedes firmarlo manualmente entrando a la App o Web de Binance, buscando SPYUSDT en Futuros e intentando colocar una orden para que aparezca el popup del acuerdo.")

if __name__ == "__main__":
    sign_agreement()
