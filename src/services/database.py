"""Storage facade for the platform API.

Per-user data lives in PostgreSQL and every function here requires an explicit
``user_id`` that the caller must have obtained from a validated Supabase token.
There is deliberately no tenant default: an omitted ``user_id`` is a TypeError,
not an implicit ``'default_user'`` write shared by every visitor.

SQLite is no longer a system of record. The only SQLite read left is the one-time
legacy import performed by :func:`init_db`, kept for installations upgrading from
a release that stored rows in ``config/quantum_llama.db``.
"""
import os
import sys
from typing import Any, Dict, List, Optional

from src.utils.paths import get_data_path

from src.services.user_repository import (
    DEFAULT_USER_ID,
    DatabaseNotConfigured,
    get_repository,
    reset_repository,
    set_repository,
)

# Broker accounts are stored per user in PostgreSQL, one row per account and
# platform, with the credentials encrypted under that user's own key.
BROKER_PLATFORMS = ("mt5", "crypto", "nt8")

# Legacy key files the previous release encrypted each platform with.
LEGACY_KEY_FILES = {
    "mt5": ".mt5_key",
    "crypto": ".crypto_key",
    "nt8": ".mt5_key",
    "tradovate": ".tradovate_key",
}


def get_db_path():
    # If running as a PyInstaller bundle, use APPDATA for persistence
    if getattr(sys, 'frozen', False):
        app_data = os.environ.get('APPDATA') or os.path.expanduser('~')
        db_dir = os.path.join(app_data, "Quantum Llama", "data")
    else:
        # Development mode
        db_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config"
        )

    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "quantum_llama.db")

def get_outputs_dir():
    if getattr(sys, 'frozen', False):
        docs_dir = os.path.join(os.path.expanduser('~'), 'Documents')
        out_dir = os.path.join(docs_dir, "Quantum Llama", "outputs")
    else:
        out_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "outputs"
        )
    os.makedirs(out_dir, exist_ok=True)
    return out_dir

def get_logs_dir():
    if getattr(sys, 'frozen', False):
        app_data = os.environ.get('APPDATA') or os.path.expanduser('~')
        log_dir = os.path.join(app_data, "Quantum Llama", "logs")
    else:
        log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs"
        )
    os.makedirs(log_dir, exist_ok=True)
    return log_dir

def init_db():
    """Create the Postgres schema and run the one-time legacy imports."""
    repository = get_repository()
    repository.ensure_schema()
    result = repository.import_legacy_sqlite(get_db_path())
    accounts = import_legacy_accounts()
    print(
        "[DATABASE] PostgreSQL schema ready; "
        f"legacy SQLite import: {result['status']}; "
        f"legacy account import: {accounts['status']}"
    )

def legacy_import_user_id() -> str:
    """Identity the legacy import writes to."""
    from src.services.user_repository import legacy_import_user_id as resolve
    return resolve()


def delete_user_rows(user_id: str) -> Dict[str, int]:
    """Destructive helper for an explicit replace import."""
    return get_repository().delete_user_rows(user_id)


def clear_legacy_import_marker() -> None:
    """Allow one further import at the operator's explicit request."""
    get_repository().clear_legacy_import_marker()


def legacy_table_counts(sqlite_path: Optional[str] = None) -> Dict[str, int]:
    """Row counts the importer would see, without exposing any row.
    """
    from src.services.user_repository import _read_legacy_rows
    rows = _read_legacy_rows(sqlite_path or get_db_path())
    if rows is None:
        return {}
    return {table: len(values) for table, values in rows.items()}


def legacy_import_already_applied() -> bool:
    """Whether the one-time desktop import has already been recorded."""
    return get_repository().legacy_import_applied()


def import_legacy_sqlite(sqlite_path: Optional[str] = None) -> Dict[str, Any]:
    """Expose the compatibility import for operators and tests."""
    return get_repository().import_legacy_sqlite(sqlite_path or get_db_path())

def get_settings(*, user_id: str) -> Dict[str, Any]:
    return get_repository().get_settings(user_id)

def save_settings(data: Dict[str, Any], *, user_id: str) -> bool:
    return get_repository().save_settings(user_id, data)

def get_workspace(session_name: str, *, user_id: str) -> Optional[Dict[str, Any]]:
    return get_repository().get_workspace(user_id, session_name)

def save_workspace(session_name: str, data: Dict[str, Any], *, user_id: str) -> bool:
    return get_repository().save_workspace(user_id, session_name, data)

def get_last_active_workspace(*, user_id: str) -> str:
    return get_repository().get_last_active_workspace(user_id)

def set_last_active_workspace(session_name: str, *, user_id: str) -> bool:
    return get_repository().set_last_active_workspace(user_id, session_name)

def get_all_workspaces(*, user_id: str) -> Dict[str, Dict[str, Any]]:
    return get_repository().get_all_workspaces(user_id)

def delete_workspace(session_name: str, *, user_id: str) -> bool:
    return get_repository().delete_workspace(user_id, session_name)

def legacy_account_files() -> Dict[str, str]:
    """Paths the previous release wrote each platform's accounts to.

    They resolve through the shared data-path helper, which is the project root
    inside a container (``/app/src/config``) - that is where every account a web
    user created actually went, and it is what this one-time import must read.
    """
    return {
        platform: get_data_path("src", "config", f"{platform}_accounts.json")
        for platform in BROKER_PLATFORMS
    }


def _legacy_account_blob(platform: str, entry: Dict[str, Any]) -> str:
    """Re-encrypt one legacy secret under its owner's per-user key.

    The legacy files hold ciphertext for the installation-wide key file. When that
    key is still present the secret is decrypted and re-encrypted for the owner;
    when it is gone the account is still imported, with an empty blob, so nothing
    undecryptable is ever stored. This never raises: an unwritable key location
    must not stop startup.
    """
    try:
        from src.services.credential_manager import (
            SECRET_FIELDS,
            encrypt_secrets,
            get_vault,
        )
        from src.services.security import CredentialManager

        fields = SECRET_FIELDS.get(platform, ())
        if not fields:
            return ""
        owner = legacy_import_user_id()
        legacy_cipher = None
        secrets: Dict[str, str] = {}
        for field in fields:
            stored = entry.get(field)
            if not isinstance(stored, str) or not stored:
                continue
            if legacy_cipher is None:
                legacy_cipher = CredentialManager(
                    key_file=LEGACY_KEY_FILES.get(platform, ".mt5_key")
                )
            plaintext = legacy_cipher.decrypt(stored)
            if plaintext and plaintext != "DECRYPTION_FAILED":
                secrets[field] = plaintext
        return encrypt_secrets(get_vault().manager_for(owner), platform, secrets)
    except Exception:
        return ""


def import_legacy_accounts(
    files: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """One-time import of the legacy JSON account files into Postgres."""
    return get_repository().import_legacy_accounts(
        legacy_account_files() if files is None else files,
        blob_builder=_legacy_account_blob,
    )


def clear_legacy_account_import_marker() -> None:
    """Allow one further account import at the operator's explicit request."""
    from src.services.user_repository import LEGACY_ACCOUNT_IMPORT_MARKER

    get_repository().clear_legacy_import_marker(LEGACY_ACCOUNT_IMPORT_MARKER)


def list_accounts(*, user_id: str) -> List[Dict[str, Any]]:
    return get_repository().list_accounts(user_id=user_id)

def get_account(*, user_id: str, platform: str, account_id: str) -> Optional[Dict[str, Any]]:
    return get_repository().get_account(
        user_id=user_id, platform=platform, account_id=account_id
    )

def upsert_account(
    *,
    user_id: str,
    platform: str,
    account_id: str,
    metadata: Dict[str, Any],
    credential_blob: str = "",
) -> bool:
    return get_repository().upsert_account(
        user_id=user_id,
        platform=platform,
        account_id=account_id,
        metadata=metadata,
        credential_blob=credential_blob,
    )

def delete_account(*, user_id: str, platform: str, account_id: str) -> bool:
    return get_repository().delete_account(
        user_id=user_id, platform=platform, account_id=account_id
    )

def get_ai_chat_history(*, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    return get_repository().get_ai_chat_history(user_id, limit=limit)

def save_ai_chat_message(
    role: str,
    content: str,
    skill: str = None,
    agent_actions: Dict = None,
    *,
    user_id: str,
) -> None:
    return get_repository().save_ai_chat_message(
        user_id, role, content, skill=skill, agent_actions=agent_actions
    )

def clear_ai_chat_history(*, user_id: str) -> None:
    return get_repository().clear_ai_chat_history(user_id)

def get_algolab_state(*, user_id: str) -> Dict[str, Any]:
    return get_repository().get_algolab_state(user_id)

def save_algolab_state(state: Dict[str, Any], *, user_id: str) -> None:
    return get_repository().save_algolab_state(user_id, state)
