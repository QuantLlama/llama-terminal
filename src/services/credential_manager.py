"""Per-user credential encryption for broker accounts.

Broker accounts moved from ``src/config/<platform>_accounts.json`` into
PostgreSQL, where every row belongs to one authenticated user. A single
installation-wide Fernet key would still let one user's ciphertext be decrypted
on another user's behalf, so this module derives one key per ``user_id`` from one
installation master secret (HMAC-SHA256, the derived key base64-urlsafe encoded
for Fernet) and keeps the ``CredentialManager`` semantics the rest of the
codebase relies on:

* ``encrypt("")`` returns ``""``,
* ``decrypt("")`` returns ``""``,
* a blob that cannot be decrypted returns ``"DECRYPTION_FAILED"`` instead of
  raising or leaking an exception message.

The master secret comes from ``QL_CREDENTIAL_MASTER_KEY`` when the operator
provides it (the supported deployment path), otherwise from the installation key
file resolved through ``QUANTUM_LLAMA_KEY_DIR`` exactly like the other Fernet
keys. Account ciphertext is therefore never decryptable with another user's key
material, and the plaintext never leaves this module.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from typing import Any, Dict, Mapping, Optional, Tuple

from cryptography.fernet import Fernet

from src.services.security import CredentialManager

logger = logging.getLogger(__name__)

MASTER_KEY_ENV = "QL_CREDENTIAL_MASTER_KEY"
MASTER_KEY_FILE = ".broker_accounts_master_key"
KEY_DERIVATION_SALT = b"quantum-llama/broker-accounts/v1"

# Fields that hold a secret. They are encrypted into the account's
# ``credential_blob`` column and never written to ``metadata``.
SECRET_FIELDS: Dict[str, Tuple[str, ...]] = {
    "mt5": ("password",),
    "crypto": ("api_secret", "passphrase"),
    "tradovate": ("password", "sec"),
    "nt8": (),
}


def _master_key_from_environment() -> bytes:
    """Return the installation master secret, creating the fallback file once."""
    configured = (os.environ.get(MASTER_KEY_ENV) or "").strip()
    if configured:
        return configured.encode("utf-8")
    # Reuses the existing key-file location rules, including QUANTUM_LLAMA_KEY_DIR.
    return CredentialManager(key_file=MASTER_KEY_FILE).key


class UserCredentialCipher:
    """Fernet cipher scoped to exactly one tenant."""

    def __init__(self, key: bytes):
        self.key = key
        self.cipher = Fernet(key)

    def encrypt(self, data: Optional[str]) -> str:
        if not data:
            return ""
        return self.cipher.encrypt(str(data).encode()).decode()

    def decrypt(self, encrypted_data: Optional[str]) -> str:
        if not encrypted_data or encrypted_data == "DECRYPTION_FAILED":
            return ""
        try:
            return self.cipher.decrypt(encrypted_data.encode()).decode()
        except Exception as exc:  # InvalidToken and malformed input alike
            logger.error("Decryption failed for a user credential blob: %s", exc)
            return "DECRYPTION_FAILED"


class UserCredentialVault:
    """Derives and caches one non-interchangeable key per tenant."""

    def __init__(self, master_key: Optional[bytes] = None):
        self._master_key = master_key or _master_key_from_environment()
        self._ciphers: Dict[str, UserCredentialCipher] = {}

    def key_for(self, user_id: str) -> bytes:
        if not isinstance(user_id, str) or not user_id.strip():
            raise TypeError(
                "user_id is required to derive a per-user credential key; "
                "there is no shared tenant key"
            )
        digest = hmac.new(
            self._master_key,
            KEY_DERIVATION_SALT + b"|" + user_id.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(digest)

    def manager_for(self, user_id: str) -> UserCredentialCipher:
        cipher = self._ciphers.get(user_id)
        if cipher is None:
            cipher = UserCredentialCipher(self.key_for(user_id))
            self._ciphers[user_id] = cipher
        return cipher


def split_secrets(platform: str, account: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Separate the public account fields from the plaintext secrets."""
    secret_fields = SECRET_FIELDS.get(platform, ())
    metadata = {
        key: value for key, value in account.items() if key not in secret_fields
    }
    secrets = {
        field: account[field]
        for field in secret_fields
        if isinstance(account.get(field), str) and account[field]
    }
    return metadata, secrets


def encrypt_secrets(
    cipher: UserCredentialCipher, platform: str, secrets: Mapping[str, Any]
) -> str:
    """Encrypt this platform's secrets into one blob (``""`` when there are none)."""
    secret_fields = SECRET_FIELDS.get(platform, ())
    payload = {
        field: value
        for field, value in secrets.items()
        if field in secret_fields and isinstance(value, str) and value
    }
    if not payload:
        return ""
    return cipher.encrypt(json.dumps(payload, sort_keys=True))


def decrypt_secrets(
    cipher: UserCredentialCipher, platform: str, blob: Optional[str]
) -> Dict[str, str]:
    """Decrypt one blob; unreadable or foreign blobs yield no secrets at all."""
    if not blob:
        return {}
    plaintext = cipher.decrypt(blob)
    if plaintext in ("", "DECRYPTION_FAILED"):
        return {}
    try:
        payload = json.loads(plaintext)
    except (TypeError, ValueError):
        logger.error("A credential blob did not contain the expected JSON payload")
        return {}
    if not isinstance(payload, dict):
        return {}
    secret_fields = SECRET_FIELDS.get(platform, ())
    return {
        field: value
        for field, value in payload.items()
        if field in secret_fields and isinstance(value, str)
    }


_vault: Optional[UserCredentialVault] = None


def get_vault() -> UserCredentialVault:
    """Return the process vault, created from the installation secret on first use."""
    global _vault
    if _vault is None:
        _vault = UserCredentialVault()
    return _vault


def set_vault(vault: Optional[UserCredentialVault]) -> None:
    """Install a vault (tests and operational overrides)."""
    global _vault
    _vault = vault


def reset_vault() -> None:
    global _vault
    _vault = None


def user_cipher(user_id: str) -> UserCredentialCipher:
    """Convenience accessor used by the account managers."""
    return get_vault().manager_for(user_id)
