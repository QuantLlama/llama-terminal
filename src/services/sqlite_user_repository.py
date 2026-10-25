"""Per-user storage for a local run, backed by a SQLite file on disk.

A local operator should not pay the cloud round trip for their own workspaces,
settings, chat log, AlgoLab state or broker account list. This repository
implements exactly the contract of :class:`PostgresUserRepository` - same method
names, same arguments, same returned dicts/lists/booleans - so the only thing
that changes is the dialect underneath: ``INTEGER PRIMARY KEY AUTOINCREMENT``
instead of ``BIGSERIAL``, named ``:parameter`` placeholders instead of pyformat,
no ``::jsonb`` casts, and JSON columns stored as the same JSON text the Postgres
repository already writes.

It is created only when ``QLLAMA_STORAGE=sqlite`` (see
``user_repository.get_repository``). An unset switch keeps the cloud on
PostgreSQL, and nothing here ever opens a network connection.

Two pragmas make one connection per call safe: ``journal_mode=WAL`` lets readers
and the writer overlap, and ``busy_timeout`` makes a concurrent writer wait
instead of failing. ``check_same_thread=False`` matches how the API handlers
reach a shared repository from worker threads.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.services.user_repository import (
    ALGOLAB_COLUMNS,
    CHAT_COLUMNS,
    LEGACY_ACCOUNT_IMPORT_MARKER,
    LEGACY_IMPORT_DISABLE_ENV,
    LEGACY_IMPORT_MARKER,
    SETTINGS_COLUMNS,
    WORKSPACE_COLUMNS,
    _ALGOLAB_DEFAULTS,
    _SETTINGS_DEFAULTS,
    _WORKSPACE_DEFAULTS,
    _algolab_values,
    _broker_account_row,
    _broker_account_values,
    _chat_values,
    _flag,
    _insert_sql,
    _legacy_account_metadata,
    _legacy_values,
    _read_legacy_account_file,
    _read_legacy_rows,
    _settings_row,
    _settings_values,
    _workspace_row,
    _workspace_values,
    legacy_import_user_id,
)

# Rows are always read back through the same mappers as the Postgres repository,
# so a value that survives one store survives the other.
__all__ = ["SqliteUserRepository", "SQLITE_SCHEMA_STATEMENTS", "default_sqlite_path"]

_PLACEHOLDER = ":{}"

SQLITE_SCHEMA_STATEMENTS: Tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS user_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        platform TEXT DEFAULT 'mt5',
        theme TEXT DEFAULT 'dark',
        show_grid INTEGER DEFAULT 1,
        show_watermark INTEGER DEFAULT 1,
        one_click_trading INTEGER DEFAULT 0,
        timer_enabled INTEGER DEFAULT 1,
        timer_position TEXT DEFAULT 'bottom',
        timer_size TEXT DEFAULT 'medium',
        timer_color TEXT DEFAULT '#fbbf24',
        timer_show_progress INTEGER DEFAULT 1,
        last_active_workspace TEXT DEFAULT 'session_mt5',
        extra_settings TEXT DEFAULT '{}',
        chart_candle_up TEXT DEFAULT '#10b981',
        chart_candle_down TEXT DEFAULT '#ef4444',
        chart_bg_color TEXT DEFAULT '#111111',
        chart_candle_border_visible INTEGER DEFAULT 0,
        chart_candle_border_color TEXT DEFAULT '#ffffff',
        risk_max_daily_loss REAL DEFAULT 500.0,
        risk_max_contracts INTEGER DEFAULT 1,
        risk_emotional_guard INTEGER DEFAULT 0,
        risk_locked_until TEXT,
        updated_at TEXT,
        CONSTRAINT user_settings_user_id_key UNIQUE (user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS workspaces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        session_name TEXT NOT NULL,
        layout TEXT DEFAULT 'single',
        charts TEXT DEFAULT '[]',
        active_chart_id INTEGER DEFAULT 1,
        symbol TEXT DEFAULT 'MNQ',
        timeframe TEXT DEFAULT '1m',
        show_tape INTEGER DEFAULT 1,
        show_order_entry INTEGER DEFAULT 1,
        drawings TEXT DEFAULT '[]',
        panel_sizes TEXT DEFAULT '{}',
        symbol_settings TEXT DEFAULT '{}',
        indicator_settings TEXT DEFAULT '{}',
        visibility_settings TEXT DEFAULT '{}',
        show_dom INTEGER DEFAULT 0,
        chart_settings TEXT DEFAULT '{}',
        updated_at TEXT,
        CONSTRAINT workspaces_user_session_key UNIQUE (user_id, session_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        skill TEXT,
        agent_actions TEXT,
        timestamp TEXT DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS algolab_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        open_files TEXT DEFAULT '[]',
        file_contents TEXT DEFAULT '{}',
        active_file_path TEXT,
        is_chat_open INTEGER DEFAULT 0,
        chat_width INTEGER DEFAULT 350,
        updated_at TEXT,
        CONSTRAINT algolab_state_user_id_key UNIQUE (user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS broker_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        platform TEXT NOT NULL,
        account_id TEXT NOT NULL,
        metadata TEXT NOT NULL DEFAULT '{}',
        credential_blob TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CONSTRAINT broker_accounts_user_platform_account_key
            UNIQUE (user_id, platform, account_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS migration_state (
        name TEXT PRIMARY KEY,
        applied_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_settings_user_id ON user_settings (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_workspaces_user_id ON workspaces (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_ai_chat_history_user_id ON ai_chat_history (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_algolab_state_user_id ON algolab_state (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_broker_accounts_user_id ON broker_accounts (user_id)",
)

# SQLite has no ``ADD COLUMN IF NOT EXISTS``, so the columns a pre-migration file
# may lack are declared here and added only when ``PRAGMA table_info`` misses them.
SQLITE_ADDED_COLUMNS: Tuple[Tuple[str, str, str], ...] = (
    ("user_settings", "extra_settings", "TEXT DEFAULT '{}'"),
    ("user_settings", "risk_max_daily_loss", "REAL DEFAULT 500.0"),
    ("user_settings", "risk_max_contracts", "INTEGER DEFAULT 1"),
    ("user_settings", "risk_emotional_guard", "INTEGER DEFAULT 0"),
    ("user_settings", "risk_locked_until", "TEXT"),
    ("workspaces", "show_dom", "INTEGER DEFAULT 0"),
    ("workspaces", "chart_settings", "TEXT DEFAULT '{}'"),
    ("algolab_state", "is_chat_open", "INTEGER DEFAULT 0"),
    ("algolab_state", "chat_width", "INTEGER DEFAULT 350"),
)

_SETTINGS_UPSERT = _insert_sql(
    "user_settings", SETTINGS_COLUMNS, ("user_id",), True, _PLACEHOLDER
)
_SETTINGS_LEGACY_INSERT = _insert_sql(
    "user_settings", SETTINGS_COLUMNS, ("user_id",), False, _PLACEHOLDER
)
_WORKSPACE_UPSERT = _insert_sql(
    "workspaces", WORKSPACE_COLUMNS, ("user_id", "session_name"), True, _PLACEHOLDER
)
_WORKSPACE_LEGACY_INSERT = _insert_sql(
    "workspaces", WORKSPACE_COLUMNS, ("user_id", "session_name"), False, _PLACEHOLDER
)
_CHAT_INSERT = _insert_sql("ai_chat_history", CHAT_COLUMNS, (), False, _PLACEHOLDER)
_ALGOLAB_UPSERT = _insert_sql(
    "algolab_state", ALGOLAB_COLUMNS, ("user_id",), True, _PLACEHOLDER
)
_ALGOLAB_LEGACY_INSERT = _insert_sql(
    "algolab_state", ALGOLAB_COLUMNS, ("user_id",), False, _PLACEHOLDER
)

# Same shape as the Postgres statement: ``created_at`` is not updated, so a
# re-saved account keeps the timestamp of its first insert.
_BROKER_ACCOUNT_UPSERT = """
INSERT INTO broker_accounts
    (user_id, platform, account_id, metadata, credential_blob, created_at, updated_at)
VALUES (
    :user_id, :platform, :account_id, :metadata,
    :credential_blob, :created_at, :updated_at
)
ON CONFLICT (user_id, platform, account_id) DO UPDATE SET
    metadata = excluded.metadata,
    credential_blob = excluded.credential_blob,
    updated_at = excluded.updated_at
"""

_BROKER_ACCOUNT_LEGACY_INSERT = """
INSERT INTO broker_accounts
    (user_id, platform, account_id, metadata, credential_blob, created_at, updated_at)
VALUES (
    :user_id, :platform, :account_id, :metadata,
    :credential_blob, :created_at, :updated_at
)
ON CONFLICT (user_id, platform, account_id) DO NOTHING
"""

_MARKER_INSERT = """
INSERT INTO migration_state (name, applied_at)
VALUES (:name, :applied_at)
ON CONFLICT (name) DO NOTHING
"""


def default_sqlite_path() -> str:
    """The local file a run without ``QLLAMA_SQLITE_PATH`` uses.

    Resolved from this module, never from the current directory, so the switch
    behaves the same however the API was started: ``<project>/config/quantum_llama.db``.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, "config", "quantum_llama.db")


class SqliteUserRepository:
    """Tenant-scoped storage operations over one SQLite file."""

    def __init__(self, path: str):
        if not path:
            raise ValueError("A SQLite database path is required")
        self.path = str(path)

    def _connect(self) -> sqlite3.Connection:
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        connection = sqlite3.connect(
            self.path,
            check_same_thread=False,
            timeout=30.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @contextmanager
    def _cursor(self):
        connection = self._connect()
        try:
            cursor = connection.cursor()
            yield cursor
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # ── schema ────────────────────────────────────────────────────

    def ensure_schema(self) -> None:
        with self._cursor() as cursor:
            for statement in SQLITE_SCHEMA_STATEMENTS:
                cursor.execute(statement)
            for table, column, declaration in SQLITE_ADDED_COLUMNS:
                existing = {
                    row["name"]
                    for row in cursor.execute(f"PRAGMA table_info({table})")
                }
                if column not in existing:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    # ── settings ──────────────────────────────────────────────────

    def get_settings(self, user_id: str) -> Dict[str, Any]:
        with self._cursor() as cursor:
            row = cursor.execute(
                "SELECT * FROM user_settings WHERE user_id = :user_id",
                {"user_id": user_id},
            ).fetchone()
        return _settings_row(dict(row)) if row else dict(_SETTINGS_DEFAULTS)

    def save_settings(self, user_id: str, data: Dict[str, Any]) -> bool:
        values = _settings_values(user_id, data, self.get_settings(user_id))
        with self._cursor() as cursor:
            cursor.execute(_SETTINGS_UPSERT, values)
        return True

    # ── workspaces ────────────────────────────────────────────────

    def get_workspace(self, user_id: str, session_name: str) -> Optional[Dict[str, Any]]:
        with self._cursor() as cursor:
            row = cursor.execute(
                """
                SELECT * FROM workspaces
                WHERE user_id = :user_id AND session_name = :session_name
                """,
                {"user_id": user_id, "session_name": session_name},
            ).fetchone()
        return _workspace_row(dict(row), detail=True) if row else None

    def save_workspace(self, user_id: str, session_name: str, data: Dict[str, Any]) -> bool:
        values = _workspace_values(user_id, session_name, data)
        with self._cursor() as cursor:
            cursor.execute(_WORKSPACE_UPSERT, values)
        return True

    def get_all_workspaces(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        with self._cursor() as cursor:
            rows = cursor.execute(
                "SELECT * FROM workspaces WHERE user_id = :user_id",
                {"user_id": user_id},
            ).fetchall()
        return {
            row["session_name"]: _workspace_row(dict(row), detail=False)
            for row in rows
        }

    def delete_workspace(self, user_id: str, session_name: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM workspaces
                WHERE user_id = :user_id AND session_name = :session_name
                """,
                {"user_id": user_id, "session_name": session_name},
            )
            return cursor.rowcount > 0

    def get_last_active_workspace(self, user_id: str) -> str:
        return self.get_settings(user_id).get("last_active_workspace", "session_mt5")

    def set_last_active_workspace(self, user_id: str, session_name: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_settings (user_id, last_active_workspace, updated_at)
                VALUES (:user_id, :last_active_workspace, :updated_at)
                ON CONFLICT (user_id) DO UPDATE SET
                    last_active_workspace = excluded.last_active_workspace,
                    updated_at = excluded.updated_at
                """,
                {
                    "user_id": user_id,
                    "last_active_workspace": session_name,
                    "updated_at": datetime.now().isoformat(),
                },
            )
            return cursor.rowcount > 0

    # ── ai chat history ───────────────────────────────────────────

    def get_ai_chat_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._cursor() as cursor:
            rows = cursor.execute(
                """
                SELECT * FROM ai_chat_history
                WHERE user_id = :user_id
                ORDER BY id ASC
                LIMIT :limit
                """,
                {"user_id": user_id, "limit": limit},
            ).fetchall()
        return [
            {
                "role": row["role"],
                "content": row["content"],
                "skill": row.get("skill"),
                "agent_actions": json.loads(row["agent_actions"])
                if row.get("agent_actions")
                else None,
                "timestamp": row.get("timestamp"),
            }
            for row in (dict(found) for found in rows)
        ]

    def save_ai_chat_message(
        self,
        user_id: str,
        role: str,
        content: str,
        skill: Optional[str] = None,
        agent_actions: Optional[Dict[str, Any]] = None,
    ) -> None:
        values = _chat_values(user_id, role, content, skill, agent_actions)
        with self._cursor() as cursor:
            cursor.execute(_CHAT_INSERT, values)

    def clear_ai_chat_history(self, user_id: str) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                "DELETE FROM ai_chat_history WHERE user_id = :user_id",
                {"user_id": user_id},
            )

    # ── algolab state ─────────────────────────────────────────────

    def get_algolab_state(self, user_id: str) -> Dict[str, Any]:
        with self._cursor() as cursor:
            row = cursor.execute(
                "SELECT * FROM algolab_state WHERE user_id = :user_id",
                {"user_id": user_id},
            ).fetchone()
        if not row:
            return {
                "open_files": [],
                "file_contents": {},
                "active_file_path": None,
                "is_chat_open": False,
                "chat_width": 350,
            }
        state = dict(row)
        return {
            "open_files": json.loads(state["open_files"]) if state.get("open_files") else [],
            "file_contents": json.loads(state["file_contents"])
            if state.get("file_contents")
            else {},
            "active_file_path": state.get("active_file_path"),
            "is_chat_open": _flag(state.get("is_chat_open")),
            "chat_width": state.get("chat_width") or 350,
        }

    def save_algolab_state(self, user_id: str, state: Dict[str, Any]) -> None:
        values = _algolab_values(user_id, state)
        with self._cursor() as cursor:
            cursor.execute(_ALGOLAB_UPSERT, values)

    # ── broker accounts ───────────────────────────────────────────

    def list_accounts(self, *, user_id: str) -> List[Dict[str, Any]]:
        """Every account owned by one tenant, across all broker platforms."""
        with self._cursor() as cursor:
            rows = cursor.execute(
                """
                SELECT * FROM broker_accounts
                WHERE user_id = :user_id
                ORDER BY platform ASC, account_id ASC
                """,
                {"user_id": user_id},
            ).fetchall()
        return [_broker_account_row(dict(row)) for row in rows]

    def get_account(
        self, *, user_id: str, platform: str, account_id: str
    ) -> Optional[Dict[str, Any]]:
        with self._cursor() as cursor:
            row = cursor.execute(
                """
                SELECT * FROM broker_accounts
                WHERE user_id = :user_id
                  AND platform = :platform
                  AND account_id = :account_id
                """,
                {"user_id": user_id, "platform": platform, "account_id": account_id},
            ).fetchone()
        return _broker_account_row(dict(row)) if row else None

    def upsert_account(
        self,
        *,
        user_id: str,
        platform: str,
        account_id: str,
        metadata: Dict[str, Any],
        credential_blob: str = "",
    ) -> bool:
        """Create or update one account of one tenant."""
        values = _broker_account_values(
            user_id=user_id,
            platform=platform,
            account_id=account_id,
            metadata=metadata,
            credential_blob=credential_blob,
        )
        with self._cursor() as cursor:
            cursor.execute(_BROKER_ACCOUNT_UPSERT, values)
        return True

    def delete_account(self, *, user_id: str, platform: str, account_id: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM broker_accounts
                WHERE user_id = :user_id
                  AND platform = :platform
                  AND account_id = :account_id
                """,
                {"user_id": user_id, "platform": platform, "account_id": account_id},
            )
            return cursor.rowcount > 0

    def import_legacy_accounts(
        self,
        files: Optional[Dict[str, str]] = None,
        *,
        marker: str = LEGACY_ACCOUNT_IMPORT_MARKER,
        blob_builder=None,
    ) -> Dict[str, Any]:
        """Copy the legacy ``*_accounts.json`` files into the file exactly once.

        Same marker discipline as the Postgres repository: the marker row and
        every account row share one transaction, existing rows are never
        overwritten, and a missing or unreadable file is skipped rather than
        raising.
        """
        sources = dict(files or {})
        loaded = {
            platform: _read_legacy_account_file(path)
            for platform, path in sources.items()
        }
        imported = {platform: 0 for platform in sources}
        if not any(entries is not None for entries in loaded.values()):
            return {"status": "skipped_missing_file", "imported": imported}

        identity = legacy_import_user_id()
        now = datetime.now().isoformat()
        with self._cursor() as cursor:
            cursor.execute(_MARKER_INSERT, {"name": marker, "applied_at": now})
            if cursor.rowcount == 0:
                return {"status": "skipped_already_applied", "imported": {}}
            for platform, entries in loaded.items():
                for entry in entries or []:
                    account_id = str(entry.get("id") or "").strip()
                    if not account_id:
                        continue
                    values = {
                        "user_id": identity,
                        "platform": platform,
                        "account_id": account_id,
                        "metadata": json.dumps(
                            _legacy_account_metadata(platform, entry)
                        ),
                        "credential_blob": blob_builder(platform, entry)
                        if blob_builder
                        else "",
                        "created_at": str(entry.get("created_at") or now),
                        "updated_at": now,
                    }
                    cursor.execute(_BROKER_ACCOUNT_LEGACY_INSERT, values)
                    imported[platform] += cursor.rowcount
        return {"status": "applied", "imported": imported}

    # ── legacy SQLite compatibility import ────────────────────────

    def clear_legacy_import_marker(self, marker: str = LEGACY_IMPORT_MARKER) -> None:
        """Drop the marker so a deliberate re-import can run once more."""
        with self._cursor() as cursor:
            cursor.execute(
                "DELETE FROM migration_state WHERE name = :name", {"name": marker}
            )

    def delete_user_rows(self, user_id: str) -> Dict[str, int]:
        """Remove one tenant's rows before a deliberate replace import."""
        if not user_id:
            raise ValueError("user_id is required")
        removed: Dict[str, int] = {}
        with self._cursor() as cursor:
            for table in ("ai_chat_history", "workspaces", "algolab_state", "user_settings"):
                cursor.execute(
                    f"DELETE FROM {table} WHERE user_id = :user_id",
                    {"user_id": user_id},
                )
                removed[table] = cursor.rowcount
        return removed

    def legacy_import_applied(self, marker: str = LEGACY_IMPORT_MARKER) -> bool:
        """True when the one-time import marker is already recorded."""
        with self._cursor() as cursor:
            return (
                cursor.execute(
                    "SELECT 1 FROM migration_state WHERE name = :name",
                    {"name": marker},
                ).fetchone()
                is not None
            )

    def import_legacy_sqlite(
        self, sqlite_path: Optional[str], marker: str = LEGACY_IMPORT_MARKER
    ) -> Dict[str, Any]:
        """Copy pre-migration rows from *another* SQLite file into this one, once.

        Importing the file this repository already serves is a no-op: the rows
        are the ones it reads anyway. Everything else follows the Postgres
        contract - one transaction, a marker row, and never overwriting an
        existing row.
        """
        if (os.environ.get(LEGACY_IMPORT_DISABLE_ENV) or "").strip().lower() in {
            "1", "true", "yes", "on",
        }:
            return {"status": "disabled", "imported": {}}
        if not sqlite_path or not os.path.exists(sqlite_path):
            return {"status": "skipped_missing_file", "imported": {}}
        if os.path.abspath(sqlite_path) == os.path.abspath(self.path):
            return {"status": "skipped_same_file", "imported": {}}
        legacy = _read_legacy_rows(sqlite_path)
        if legacy is None:
            return {"status": "skipped_unreadable_file", "imported": {}}

        imported = {table: 0 for table in legacy}
        with self._cursor() as cursor:
            cursor.execute(
                _MARKER_INSERT,
                {"name": marker, "applied_at": datetime.now().isoformat()},
            )
            if cursor.rowcount == 0:
                return {"status": "skipped_already_applied", "imported": {}}
            plans = (
                ("user_settings", _SETTINGS_LEGACY_INSERT, SETTINGS_COLUMNS,
                 {**_SETTINGS_DEFAULTS, "updated_at": None}),
                ("workspaces", _WORKSPACE_LEGACY_INSERT, WORKSPACE_COLUMNS,
                 {**_WORKSPACE_DEFAULTS, "updated_at": None}),
                ("algolab_state", _ALGOLAB_LEGACY_INSERT, ALGOLAB_COLUMNS,
                 {**_ALGOLAB_DEFAULTS, "updated_at": None}),
            )
            for table, statement, columns, defaults in plans:
                for row in legacy.get(table, []):
                    cursor.execute(statement, _legacy_values(row, columns, defaults))
                    imported[table] += cursor.rowcount
            for row in legacy.get("ai_chat_history", []):
                values = _legacy_values(
                    row, CHAT_COLUMNS, {"skill": None, "agent_actions": None}
                )
                if not values.get("content"):
                    continue
                cursor.execute(_CHAT_INSERT, values)
                imported["ai_chat_history"] += cursor.rowcount
        return {"status": "applied", "imported": imported}
