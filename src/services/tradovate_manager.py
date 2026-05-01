import os
import json
import hashlib
from typing import Dict, List, Optional
from datetime import datetime
import logging
from .security import CredentialManager
logger = logging.getLogger(__name__)
from src.utils.paths import get_data_path

class TradovateAccountManager:
    def __init__(self, accounts_file: str = "src/config/tradovate_accounts.json"):
        self.accounts_file = get_data_path(accounts_file)
        self.credential_manager = CredentialManager(key_file=".tradovate_key")
        self.accounts = self._load_accounts()
    def _load_accounts(self) -> Dict:
        if os.path.exists(self.accounts_file):
            try:
                with open(self.accounts_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading tradovate accounts: {e}")
                return {}
        return {}
    def _save_accounts(self):
        os.makedirs(os.path.dirname(self.accounts_file), exist_ok=True)
        with open(self.accounts_file, 'w') as f:
            json.dump(self.accounts, f, indent=4)
    def add_account(self, name: str, username: str, password: str, 
                   app_id: str, app_version: str, cid: str, sec: str,
                   environment: str = "demo") -> Dict:
        account_id = hashlib.md5(f"tradovate_{username}_{cid[:8]}".encode()).hexdigest()[:8]
        encrypted_pass = self.credential_manager.encrypt(password)
        encrypted_sec = self.credential_manager.encrypt(sec)
        account_data = {
            "id": account_id,
            "name": name,
            "broker": "Tradovate",
            "username": username,
            "password": encrypted_pass,
            "app_id": app_id,
            "app_version": app_version,
            "cid": cid,
            "sec": encrypted_sec,
            "environment": environment,
            "created_at": datetime.now().isoformat(),
            "status": "inactive",
            "is_master": False,
            "platform": "tradovate"
        }
        self.accounts[account_id] = account_data
        self._save_accounts()
        logger.info(f"Tradovate account added: {name} ({username})")
        return self._sanitize_account(account_data)
    def update_account(self, account_id: str, update_data: Dict) -> Optional[Dict]:
        if account_id not in self.accounts:
            return None
        account = self.accounts[account_id]
        fields = ["name", "username", "app_id", "app_version", "cid", "environment"]
        for field in fields:
            if field in update_data:
                account[field] = update_data[field]
        if "password" in update_data and update_data["password"]:
            account["password"] = self.credential_manager.encrypt(update_data["password"])
        if "sec" in update_data and update_data["sec"]:
            account["sec"] = self.credential_manager.encrypt(update_data["sec"])
        self.accounts[account_id] = account
        self._save_accounts()
        logger.info(f"Tradovate account updated: {account_id}")
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
            logger.info(f"Tradovate account removed: {account_id}")
            return True
        return False
    def get_accounts(self) -> List[Dict]:
        result = []
        for acc_id, acc in self.accounts.items():
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
        acc["password"] = self.credential_manager.decrypt(acc["password"])
        acc["sec"] = self.credential_manager.decrypt(acc["sec"])
        return acc
    def _sanitize_account(self, account: Dict) -> Dict:
        sanitized = account.copy()
        if "password" in sanitized:
            sanitized["password"] = "***"
        if "sec" in sanitized:
            sanitized["sec"] = "***"
        return sanitized
_manager = None
def get_tradovate_manager() -> TradovateAccountManager:
    global _manager
    if _manager is None:
        _manager = TradovateAccountManager()
    return _manager