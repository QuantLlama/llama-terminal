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

from src.services.user_repository import (
    DEFAULT_USER_ID,
    DatabaseNotConfigured,
    get_repository,
    reset_repository,
    set_repository,
)


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
    """Create the Postgres schema and run the one-time legacy import."""
    repository = get_repository()
    repository.ensure_schema()
    result = repository.import_legacy_sqlite(get_db_path())
    print(f"[DATABASE] PostgreSQL schema ready; legacy SQLite import: {result['status']}")

def clear_legacy_import_marker() -> None:
    """Allow one further import at the operator's explicit request."""
    get_repository().clear_legacy_import_marker()


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
