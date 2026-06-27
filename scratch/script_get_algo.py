import ccxt
import os
import sys
import hashlib
import hmac
import time
import requests

sys.path.append("/run/media/pabloezm/Respaldos/Pltaforma_Terminal_Llama")
from src.services.crypto_manager import get_crypto_manager

def test_get_algo():
    manager = get_crypto_manager()
    acc = manager.get_account_full("271c6a5e")
    
    api_key = acc['api_key']
    secret = acc['api_secret']
    base_url = "https://fapi.binance.com"
    endpoint = "/fapi/v1/openAlgoOrders"
    
    params = {
        'timestamp': int(time.time() * 1000)
    }
    
    query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
    signature = hmac.new(secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    query_string += f"&signature={signature}"
    
    url = f"{base_url}{endpoint}?{query_string}"
    headers = {'X-MBX-APIKEY': api_key}
    
    r = requests.get(url, headers=headers)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text}")

if __name__ == "__main__":
    test_get_algo()
