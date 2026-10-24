import os
from cryptography.fernet import Fernet
import logging
logger = logging.getLogger(__name__)
from src.utils.paths import get_data_path

class CredentialManager:
    def __init__(self, key_file: str = ".mt5_key"):
        self.key_file = self._resolve_key_path(key_file)
        self.key = self._load_or_create_key()
        self.cipher = Fernet(self.key)

    @staticmethod
    def _resolve_key_path(key_file: str) -> str:
        """QUANTUM_LLAMA_KEY_DIR overrides the default project-root location.

        Cloud deployments run as a non-root user with a read-only project
        root, so the encryption keys must live in a writable mounted volume.
        """
        key_dir = os.getenv("QUANTUM_LLAMA_KEY_DIR")
        if key_dir:
            os.makedirs(key_dir, exist_ok=True)
            return os.path.join(key_dir, key_file)
        return get_data_path(key_file)
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