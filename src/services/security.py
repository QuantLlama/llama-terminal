import os
from cryptography.fernet import Fernet
import logging
logger = logging.getLogger(__name__)
from src.utils.paths import get_data_path

class CredentialManager:
    def __init__(self, key_file: str = ".mt5_key"):
        self.key_file = get_data_path(key_file)
        self.key = self._load_or_create_key()
        self.cipher = Fernet(self.key)
    def _load_or_create_key(self) -> bytes:
        if os.path.exists(self.key_file):
            with open(self.key_file, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            return key
    def encrypt(self, data: str) -> str:
        if not data:
            return ""
        return self.cipher.encrypt(data.encode()).decode()
    def decrypt(self, encrypted_data: str) -> str:
        if not encrypted_data or encrypted_data == "DECRYPTION_FAILED":
            return ""
        try:
            return self.cipher.decrypt(encrypted_data.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return "DECRYPTION_FAILED"