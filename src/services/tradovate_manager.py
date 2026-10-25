"""Tradovate account registry.

Accounts used to live in ``src/config/tradovate_accounts.json`` and were sealed
with one installation-wide ``.tradovate_key``, so every visitor of the terminal
shared one list and one key. They now live in PostgreSQL, one row per
authenticated user, and every storage method below takes ``user_id`` as a
required keyword-only argument: there is no implicit tenant, no shared file and
no shared key leg. The username, password and the API secret are encrypted into
the row's ``credential_blob`` under the owning user's derived key (see
``credential_manager``); nothing is written under ``src/config`` any more.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional
from datetime import datetime
import logging
from src.services import database
from src.services.credential_manager import (
    decrypt_secrets,
    encrypt_secrets,
    get_vault,
    split_secrets,
)

logger = logging.getLogger(__name__)

PLATFORM = "tradovate"


class TradovateAccountManager:
    PLATFORM = PLATFORM

    def __init__(self, *, vault=None):
        self.vault = vault or get_vault()

    # ── per-user storage ──────────────────────────────────────────

    def _cipher(self, user_id: str):
        return self.vault.manager_for(user_id)

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
            account["credential_blob"] = row["credential_blob"]
            accounts[row["account_id"]] = account
        return accounts

    def _persist(
        self,
        user_id: str,
        account: Dict[str, Any],
        *,
        credential_blob: Optional[str] = None,
    ) -> None:
        """Write one account for one user, encrypting secrets under that user's key."""
        metadata, secrets = split_secrets(PLATFORM, account)
        blob = (
            encrypt_secrets(self._cipher(user_id), PLATFORM, secrets)
            if credential_blob is None
            else credential_blob
        )
        database.upsert_account(
            user_id=user_id,
            platform=PLATFORM,
            account_id=account["id"],
            metadata=metadata,
            credential_blob=blob,
        )

    def _with_secrets(self, user_id: str, account: Dict[str, Any]) -> Dict[str, Any]:
        full = {key: value for key, value in account.items() if key != "credential_blob"}
        full.update(
            decrypt_secrets(self._cipher(user_id), PLATFORM, account.get("credential_blob"))
        )
        return full

    def add_account(self, name: str, username: str, password: str,
                   app_id: str, app_version: str, cid: str, sec: str,
                   environment: str = "demo", account_type: str = "demo", *,
                   user_id: str) -> Dict:
        account_id = hashlib.md5(f"tradovate_{username}_{cid[:8]}".encode()).hexdigest()[:8]
        account_data = {
            "id": account_id,
            "name": name,
            "broker": "Tradovate",
            "username": username,
            "password": password,
            "app_id": app_id,
            "app_version": app_version,
            "cid": cid,
            "sec": sec,
            "environment": environment,
            "account_type": account_type,
            "created_at": datetime.now().isoformat(),
            "status": "inactive",
            "is_master": False,
            "platform": PLATFORM
        }
        self._persist(user_id, account_data)
        logger.info(f"Tradovate account added: {name} ({username})")
        return self._sanitize_account(account_data)

    def update_account(self, account_id: str, update_data: Dict, *, user_id: str) -> Optional[Dict]:
        stored = self._stored(user_id, account_id)
        if stored is None:
            return None
        account = dict(stored["metadata"])
        account["id"] = account_id
        secrets = decrypt_secrets(
            self._cipher(user_id), PLATFORM, stored["credential_blob"]
        )
        fields = ["name", "username", "app_id", "app_version", "cid", "environment"]
        for field in fields:
            if field in update_data:
                account[field] = update_data[field]
        if update_data.get("password"):
            secrets["password"] = update_data["password"]
        if update_data.get("sec"):
            secrets["sec"] = update_data["sec"]
        blob = encrypt_secrets(self._cipher(user_id), PLATFORM, secrets)
        self._persist(user_id, account, credential_blob=blob)
        logger.info(f"Tradovate account updated: {account_id}")
        return self._sanitize_account(account)

    def set_master_account(self, account_id: str, *, user_id: str) -> bool:
        accounts = self._stored_accounts(user_id)
        if account_id not in accounts:
            return False
        for acc_id, acc in accounts.items():
            acc["is_master"] = (acc_id == account_id)
            self._persist(user_id, acc, credential_blob=acc.get("credential_blob"))
        return True

    def remove_account(self, account_id: str, *, user_id: str) -> bool:
        if self._stored(user_id, account_id) is None:
            return False
        database.delete_account(
            user_id=user_id, platform=PLATFORM, account_id=account_id
        )
        logger.info(f"Tradovate account removed: {account_id}")
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

    def get_account_full(self, account_id: str, *, user_id: str) -> Optional[Dict]:
        """Account plus decrypted credentials, for the Tradovate connector."""
        stored = self._stored(user_id, account_id)
        if stored is None:
            return None
        account = dict(stored["metadata"])
        account["id"] = account_id
        account["credential_blob"] = stored["credential_blob"]
        return self._with_secrets(user_id, account)

    def _sanitize_account(self, account: Dict) -> Dict:
        sanitized = account.copy()
        sanitized.pop("credential_blob", None)
        for field in ("password", "sec"):
            if field in sanitized:
                sanitized[field] = "***"
        if "is_master" not in sanitized:
            sanitized["is_master"] = False
        # The accounts response requires this field; rows written before it was
        # stored still render as a demo account instead of failing validation.
        sanitized.setdefault("account_type", "demo")
        return sanitized

_manager = None

def get_tradovate_manager() -> TradovateAccountManager:
    global _manager
    if _manager is None:
        _manager = TradovateAccountManager()
    return _manager
