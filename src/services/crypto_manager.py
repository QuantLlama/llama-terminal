import os
import json
import hashlib
from typing import Dict, List, Optional
from datetime import datetime
import logging
from .security import CredentialManager
logger = logging.getLogger(__name__)
from src.utils.paths import get_data_path

class CryptoAccountManager:
    def __init__(self, accounts_file: str = "src/config/crypto_accounts.json"):
        self.accounts_file = get_data_path(accounts_file)
        self.credential_manager = CredentialManager(key_file=".crypto_key")
        self.accounts = self._load_accounts()
    def _load_accounts(self) -> Dict:
        if os.path.exists(self.accounts_file):
            try:
                with open(self.accounts_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading crypto accounts: {e}")
                return {}
        return {}
    @staticmethod
    def _is_supported_broker(broker: str) -> bool:
        return (broker or "").lower() != "bitmex"
    def _save_accounts(self):
        os.makedirs(os.path.dirname(self.accounts_file), exist_ok=True)
        with open(self.accounts_file, 'w') as f:
            json.dump(self.accounts, f, indent=4)
    def add_account(self, name: str, broker: str, api_key: str, 
                   api_secret: str, passphrase: Optional[str] = None,
                   account_type: str = "demo") -> Dict:
        if not self._is_supported_broker(broker):
            raise ValueError("BitMEX support has been removed")
        account_id = hashlib.md5(f"{broker}_{api_key[:8]}".encode()).hexdigest()[:8]
        encrypted_secret = self.credential_manager.encrypt(api_secret)
        encrypted_pass = self.credential_manager.encrypt(passphrase) if passphrase else ""
        account_data = {
            "id": account_id,
            "name": name,
            "broker": broker.lower(),
            "api_key": api_key,
            "api_secret": encrypted_secret,
            "passphrase": encrypted_pass,
            "account_type": account_type,
            "created_at": datetime.now().isoformat(),
            "status": "inactive",
            "is_master": False,
            "platform": "crypto"
        }
        self.accounts[account_id] = account_data
        self._save_accounts()
        logger.info(f"Crypto account added: {name} ({broker})")
        return self._sanitize_account(account_data)
    def update_account(self, account_id: str, update_data: Dict) -> Optional[Dict]:
        if account_id not in self.accounts:
            return None
        account = self.accounts[account_id]
        if "name" in update_data:
            account["name"] = update_data["name"]
        if "account_type" in update_data:
            account["account_type"] = update_data["account_type"]
        if "api_secret" in update_data and update_data["api_secret"]:
            account["api_secret"] = self.credential_manager.encrypt(update_data["api_secret"])
        if "passphrase" in update_data:
            account["passphrase"] = self.credential_manager.encrypt(update_data["passphrase"])
        self.accounts[account_id] = account
        self._save_accounts()
        logger.info(f"Crypto account updated: {account_id}")
        return self._sanitize_account(account)
    def set_master_account(self, account_id: str) -> bool:
        if account_id not in self.accounts:
            return False
        for acc_id, acc in self.accounts.items():
            acc["is_master"] = (acc_id == account_id)
        self._save_accounts()
        return True
    def remove_account(self, account_id: str) -> bool:
        if account_id in self.accounts:
            del self.accounts[account_id]
            self._save_accounts()
            logger.info(f"Crypto account removed: {account_id}")
            return True
        return False
    def get_accounts(self) -> List[Dict]:
        result = []
        for acc_id, acc in self.accounts.items():
            if not self._is_supported_broker(acc.get("broker")):
                continue
            sanitized = self._sanitize_account(acc)
            sanitized['id'] = acc_id  
            result.append(sanitized)
        return result
    def get_account(self, account_id: str) -> Optional[Dict]:
        if account_id in self.accounts:
            return self._sanitize_account(self.accounts[account_id])
        return None
    def get_account_full(self, account_id: str) -> Optional[Dict]:
        if account_id not in self.accounts:
            return None
        acc = self.accounts[account_id].copy()
        acc["api_secret"] = self.credential_manager.decrypt(acc["api_secret"])
        if acc.get("passphrase"):
            acc["passphrase"] = self.credential_manager.decrypt(acc["passphrase"])
        return acc
    def _sanitize_account(self, account: Dict) -> Dict:
        sanitized = account.copy()
        if "api_secret" in sanitized:
            sanitized["api_secret"] = "***"
        if "passphrase" in sanitized:
            sanitized["passphrase"] = "***" if sanitized["passphrase"] else ""
        return sanitized
_manager = None
def get_crypto_manager() -> CryptoAccountManager:
    global _manager
    if _manager is None:
        _manager = CryptoAccountManager()
    return _manager
