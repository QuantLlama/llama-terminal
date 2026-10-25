"""NinjaTrader account registry.

NinjaTrader bridges used to live in ``src/config/nt8_accounts.json``, a file the
container does not mount and every visitor shared. They now live in PostgreSQL,
one row per authenticated user, and every storage method takes ``user_id`` as a
required keyword-only argument. This platform stores no secret.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional
from datetime import datetime
import logging
from src.services import database
logger = logging.getLogger(__name__)

PLATFORM = "nt8"


class NinjaTraderAccountManager:
    PLATFORM = PLATFORM

    def __init__(self, accounts_file: str = "src/config/nt8_accounts.json"):
        # ``accounts_file`` is the legacy JSON path the one-time import reads.
        self.accounts_file = accounts_file

    # ── per-user storage ──────────────────────────────────────────

    def _stored(self, user_id: str, account_id: str) -> Optional[Dict[str, Any]]:
        return database.get_account(
            user_id=user_id, platform=PLATFORM, account_id=account_id
        )

    def _stored_accounts(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        accounts: Dict[str, Dict[str, Any]] = {}
        for row in database.list_accounts(user_id=user_id):
            if row["platform"] != PLATFORM:
                continue
            account = dict(row["metadata"])
            account["id"] = row["account_id"]
            accounts[row["account_id"]] = account
        return accounts

    @staticmethod
    def _persist(user_id: str, account: Dict[str, Any]) -> None:
        metadata = {key: value for key, value in account.items() if key != "credential_blob"}
        database.upsert_account(
            user_id=user_id,
            platform=PLATFORM,
            account_id=account["id"],
            metadata=metadata,
            credential_blob="",
        )

    def add_account(self, name: str, exchange_dir: str, account_type: str = "demo", mirror_trading: bool = True, *, user_id: str) -> Dict:
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
            "platform": PLATFORM
        }
        self._persist(user_id, account_data)
        logger.info(f"NinjaTrader bridge added: {name} -> {exchange_dir}")
        return self._sanitize_account(account_data)
    def update_account(self, account_id: str, update_data: Dict, *, user_id: str) -> Optional[Dict]:
        stored = self._stored(user_id, account_id)
        if stored is None:
            return None
        account = dict(stored["metadata"])
        account["id"] = account_id
        fields = ["name", "exchange_dir", "account_type", "mirror_trading"]
        for field in fields:
            if field in update_data:
                account[field] = update_data[field]
        self._persist(user_id, account)
        logger.info(f"NinjaTrader bridge updated: {account_id}")
        return self._sanitize_account(account)
    def set_master_account(self, account_id: str, *, user_id: str) -> bool:
        accounts = self._stored_accounts(user_id)
        if account_id not in accounts:
            return False
        for acc_id, acc in accounts.items():
            acc["is_master"] = (acc_id == account_id)
            self._persist(user_id, acc)
        return True
    def remove_account(self, account_id: str, *, user_id: str) -> bool:
        if self._stored(user_id, account_id) is None:
            return False
        database.delete_account(
            user_id=user_id, platform=PLATFORM, account_id=account_id
        )
        logger.info(f"NinjaTrader bridge removed: {account_id}")
        return True
    def get_accounts(self, *, user_id: str) -> List[Dict]:
        return [
            self._sanitize_account(acc)
            for acc in self._stored_accounts(user_id).values()
        ]
    def get_account(self, account_id: str, *, user_id: str) -> Optional[Dict]:
        stored = self._stored(user_id, account_id)
        if stored is None:
            return None
        account = dict(stored["metadata"])
        account["id"] = account_id
        return self._sanitize_account(account)
    @staticmethod
    def _sanitize_account(account: Dict) -> Dict:
        sanitized = account.copy()
        sanitized.pop("credential_blob", None)
        return sanitized
_manager = None
def get_nt8_manager() -> NinjaTraderAccountManager:
    global _manager
    if _manager is None:
        _manager = NinjaTraderAccountManager()
    return _manager
