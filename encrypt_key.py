import json
import os
import sys

# Asegurar que podemos importar src
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.services.mt5_manager import CredentialManager


def encrypt_binance_credentials():
    """
    Encripta las credenciales de Binance Demo y actualiza el archivo crypto_accounts.json.
    """
    # 1. Credenciales correctas proporcionadas por el usuario
    api_key = "zfHJdECZKeuXb3JTHW60NYaSsEYuvzWSBthxBz6ZN9QdHGI4vO7MJ1ZHwq3tXJ69"
    api_secret_raw = "oTgrC2qVjXKS5qEcVdGGKDj7Kll1uXVLx3w1t5iFYCHuplubVWKU2ytlijEfIpNM"

    # 2. Inicializar el gestor de credenciales (AES-256 interno)
    cm = CredentialManager()

    # 3. Encriptar el secreto
    encrypted_secret = cm.encrypt(api_secret_raw)
    print(f"Original Secret (primeros 5): {api_secret_raw[:5]}...")
    print(f"Encrypted Secret: {encrypted_secret[:20]}...")

    # 4. Cargar el archivo de cuentas
    accounts_path = "src/config/crypto_accounts.json"
    if not os.path.exists(accounts_path):
        print(f"Error: {accounts_path} no encontrado.")
        return

    try:
        with open(accounts_path, "r") as f:
            accounts = json.load(f)

        # 5. Encontrar y actualizar la cuenta Binance-Demo (ID: cf247ab8)
        account_id = "cf247ab8"
        if account_id in accounts:
            accounts[account_id]["api_key"] = api_key
            accounts[account_id]["api_secret"] = encrypted_secret
            print(f"Actualizando cuenta: {accounts[account_id]['name']}")

            # 6. Guardar de nuevo en el archivo
            with open(accounts_path, "w") as f:
                json.dump(accounts, f, indent=4)
            print("EXITO: Credenciales encriptadas y guardadas correctamente.")
        else:
            print(f"Error: ID de cuenta {account_id} no encontrado.")

    except Exception as e:
        print(f"ERROR CRITICO: {str(e)}")


if __name__ == "__main__":
    encrypt_binance_credentials()
