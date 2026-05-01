import os
import json
import hashlib
from typing import Dict, List, Optional
from datetime import datetime
import logging
logger = logging.getLogger(__name__)
from src.utils.paths import get_data_path

class NinjaTraderAccountManager:
    def __init__(self, accounts_file: str = "src/config/nt8_accounts.json"):
        self.accounts_file = get_data_path(accounts_file)
        self.accounts = self._load_accounts()
    def _load_accounts(self) -> Dict:
        if os.path.exists(self.accounts_file):
            try:
                with open(self.accounts_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading nt8 accounts: {e}")
                return {}
        return {}
    def _save_accounts(self):
        os.makedirs(os.path.dirname(self.accounts_file), exist_ok=True)
        with open(self.accounts_file, 'w') as f:
            json.dump(self.accounts, f, indent=4)
    def add_account(self, name: str, exchange_dir: str, account_type: str = "demo", mirror_trading: bool = True) -> Dict:
        account_id = hashlib.md5(f"nt8_{name}_{exchange_dir}".encode()).hexdigest()[:8]
        account_data = {
            "id": account_id,
            "name": name,
            "broker": "NinjaTrader",
            "exchange_dir": exchange_dir,
            "account_type": account_type,
            "mirror_trading": mirror_trading,
            "created_at": datetime.now().isoformat(),
            "status": "active", 
            "is_master": False,
            "platform": "nt8"
        }
        self.accounts[account_id] = account_data
        self._save_accounts()
        logger.info(f"NinjaTrader bridge added: {name} -> {exchange_dir}")
        return account_data
    def update_account(self, account_id: str, update_data: Dict) -> Optional[Dict]:
        if account_id not in self.accounts:
            return None
        account = self.accounts[account_id]
        fields = ["name", "exchange_dir", "account_type", "mirror_trading"]
        for field in fields:
            if field in update_data:
                account[field] = update_data[field]
        self.accounts[account_id] = account
        self._save_accounts()
        logger.info(f"NinjaTrader bridge updated: {account_id}")
        return account
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
            logger.info(f"NinjaTrader bridge removed: {account_id}")
            return True
        return False
    def get_accounts(self) -> List[Dict]:
        return list(self.accounts.values())
    def get_account(self, account_id: str) -> Optional[Dict]:
        return self.accounts.get(account_id)
_manager = None
def get_nt8_manager() -> NinjaTraderAccountManager:
    global _manager
    if _manager is None:
        _manager = NinjaTraderAccountManager()
    return _manager