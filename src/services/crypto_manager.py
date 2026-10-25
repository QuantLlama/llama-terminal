"""Crypto broker account registry.

Accounts used to live in ``src/config/crypto_accounts.json`` with one
installation-wide Fernet key, so every user shared one list and one key. They now
live in PostgreSQL, one row per authenticated user, and every storage method takes
``user_id`` as a required keyword-only argument. API secrets and passphrases are
encrypted under the owning user's derived key.
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

PLATFORM = "crypto"


class CryptoAccountManager:
    PLATFORM = PLATFORM

    def __init__(self, accounts_file: str = "src/config/crypto_accounts.json", *, vault=None):
        # ``accounts_file`` is the legacy JSON path the one-time import reads.
        self.accounts_file = accounts_file
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

    @staticmethod
    def _is_supported_broker(broker: str) -> bool:
        return (broker or "").lower() != "bitmex"

    def add_account(self, name: str, broker: str, api_key: str, 
                   api_secret: str, passphrase: Optional[str] = None,
                   account_type: str = "demo", *, user_id: str) -> Dict:
        if not self._is_supported_broker(broker):
            raise ValueError("BitMEX support has been removed")
        account_id = hashlib.md5(f"{broker}_{api_key[:8]}".encode()).hexdigest()[:8]
        account_data = {
            "id": account_id,
            "name": name,
            "broker": broker.lower(),
            "api_key": api_key,
            "api_secret": api_secret,
            "passphrase": passphrase or "",
            "account_type": account_type,
            "created_at": datetime.now().isoformat(),
            "status": "inactive",
            "is_master": False,
            "platform": PLATFORM
        }
        self._persist(user_id, account_data)
        logger.info(f"Crypto account added: {name} ({broker})")
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
        if "name" in update_data:
            account["name"] = update_data["name"]
        if "account_type" in update_data:
            account["account_type"] = update_data["account_type"]
        if update_data.get("api_secret"):
            secrets["api_secret"] = update_data["api_secret"]
        if "passphrase" in update_data:
            secrets["passphrase"] = update_data["passphrase"] or ""
        blob = encrypt_secrets(self._cipher(user_id), PLATFORM, secrets)
        self._persist(user_id, account, credential_blob=blob)
        logger.info(f"Crypto account updated: {account_id}")
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
        logger.info(f"Crypto account removed: {account_id}")
        return True
    def get_accounts(self, *, user_id: str) -> List[Dict]:
        result = []
        for acc_id, acc in self._stored_accounts(user_id).items():
            if not self._is_supported_broker(acc.get("broker")):
                continue
            sanitized = self._sanitize_account(acc)
            sanitized['id'] = acc_id
            result.append(sanitized)
        return result
    def get_account(self, account_id: str, *, user_id: str) -> Optional[Dict]:
        stored = self._stored(user_id, account_id)
        if stored is None:
            return None
        account = dict(stored["metadata"])
        account["id"] = account_id
        return self._sanitize_account(account)
    def get_account_full(self, account_id: str, *, user_id: str) -> Optional[Dict]:
        """Account plus decrypted credentials, for the local exchange connector."""
        stored = self._stored(user_id, account_id)
        if stored is None:
            return None
        account = dict(stored["metadata"])
        account["id"] = account_id
        account.update(
            decrypt_secrets(
                self._cipher(user_id), PLATFORM, stored["credential_blob"]
            )
        )
        return account
    def _sanitize_account(self, account: Dict) -> Dict:
        sanitized = account.copy()
        sanitized.pop("credential_blob", None)
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
