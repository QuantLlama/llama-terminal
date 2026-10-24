"""Per-user storage for the platform API, backed by PostgreSQL.

Every statement in this module is tenant-filtered and parameterized: identifiers
come from the static column tuples below (never from a request) and every value,
including ``user_id``, is bound as a statement parameter. There is no SQLite
fallback here; when ``DATABASE_URL`` is absent the repository refuses to exist so
callers fail loudly instead of writing to a second source of truth.

``import_legacy_sqlite`` is the one compatibility path that reads SQLite: it
copies pre-migration rows into Postgres under ``default_user`` exactly once, and
never overwrites rows that already exist in Postgres.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_USER_ID = "default_user"
DATABASE_URL_ENV = "DATABASE_URL"
LEGACY_IMPORT_DISABLE_ENV = "QL_DISABLE_LEGACY_SQLITE_IMPORT"
LEGACY_IMPORT_MARKER = "legacy_sqlite_default_user_v1"
LEGACY_IMPORT_TARGET_ENV = "QL_LEGACY_IMPORT_USER_ID"


def legacy_import_user_id() -> str:
    """Identity that receives pre-migration SQLite rows.

    A desktop owner migrating to the hosted platform sets this to their own
    account id so their workspaces and settings do not land in a shared
    placeholder. Unset keeps the historical behaviour.
    """
    raw = (os.environ.get(LEGACY_IMPORT_TARGET_ENV) or "").strip()
    if not raw:
        return DEFAULT_USER_ID
    if len(raw) > 128 or any(ch.isspace() or ch in "/\\" for ch in raw):
        raise ValueError(
            f"{LEGACY_IMPORT_TARGET_ENV} must be a single account identifier"
        )
    return raw

_SETTINGS_DEFAULTS: Dict[str, Any] = {
    "platform": "mt5",
    "theme": "dark",
    "show_grid": True,
    "show_watermark": True,
    "one_click_trading": False,
    "timer_enabled": True,
    "timer_position": "bottom",
    "timer_size": "medium",
    "timer_color": "#fbbf24",
    "timer_show_progress": True,
    "last_active_workspace": "session_mt5",
    "chart_candle_up": "#10b981",
    "chart_candle_down": "#ef4444",
    "chart_bg_color": "#111111",
    "chart_candle_border_visible": False,
    "chart_candle_border_color": "#ffffff",
    "risk_max_daily_loss": 500.0,
    "risk_max_contracts": 1,
    "risk_emotional_guard": False,
    "risk_locked_until": None,
}

_BOOLEAN_SETTINGS = (
    "show_grid",
    "show_watermark",
    "one_click_trading",
    "timer_enabled",
    "timer_show_progress",
    "chart_candle_border_visible",
    "risk_emotional_guard",
)

SETTINGS_COLUMNS: Tuple[str, ...] = (
    "user_id", "platform", "theme", "show_grid", "show_watermark",
    "one_click_trading", "timer_enabled", "timer_position", "timer_size",
    "timer_color", "timer_show_progress", "last_active_workspace",
    "chart_candle_up", "chart_candle_down", "chart_bg_color",
    "chart_candle_border_visible", "chart_candle_border_color",
    "risk_max_daily_loss", "risk_max_contracts", "risk_emotional_guard",
    "risk_locked_until", "updated_at",
)

WORKSPACE_COLUMNS: Tuple[str, ...] = (
    "user_id", "session_name", "layout", "charts", "active_chart_id",
    "symbol", "timeframe", "show_tape", "show_order_entry", "drawings",
    "panel_sizes", "symbol_settings", "indicator_settings",
    "visibility_settings", "show_dom", "chart_settings", "updated_at",
)

_WORKSPACE_DEFAULTS: Dict[str, Any] = {
    "layout": "single", "charts": "[]", "active_chart_id": 1, "symbol": "MNQ",
    "timeframe": "1m", "show_tape": 1, "show_order_entry": 1, "drawings": "[]",
    "panel_sizes": "{}", "symbol_settings": "{}", "indicator_settings": "{}",
    "visibility_settings": "{}", "show_dom": 0, "chart_settings": "{}",
}

CHAT_COLUMNS: Tuple[str, ...] = (
    "user_id", "role", "content", "skill", "agent_actions",
)

ALGOLAB_COLUMNS: Tuple[str, ...] = (
    "user_id", "open_files", "file_contents", "active_file_path",
    "is_chat_open", "chat_width", "updated_at",
)

_ALGOLAB_DEFAULTS: Dict[str, Any] = {
    "open_files": "[]", "file_contents": "{}", "active_file_path": None,
    "is_chat_open": 0, "chat_width": 350,
}


class DatabaseNotConfigured(RuntimeError):
    """Raised when per-user storage has no PostgreSQL connection string."""


def database_url() -> str:
    url = (os.environ.get(DATABASE_URL_ENV) or "").strip()
    if not url:
        raise DatabaseNotConfigured(
            "DATABASE_URL is not set. Per-user storage requires PostgreSQL; "
            "there is no sqlite fallback for authenticated data. "
            "See docs/DATA.md."
        )
    return url


def _open_connection(url: str):
    """Open a driver connection plus the row factory the repository expects."""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    return psycopg2.connect(url), RealDictCursor


def _insert_sql(
    table: str,
    columns: Tuple[str, ...],
    conflict_columns: Tuple[str, ...],
    update_on_conflict: bool,
) -> str:
    """Build a statement from static column names; values stay bound parameters."""
    column_list = ", ".join(columns)
    placeholders = ", ".join("%(" + column + ")s" for column in columns)
    conflict = ", ".join(conflict_columns)
    statement = f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})"
    if not conflict_columns:
        return statement
    if not update_on_conflict:
        return statement + f" ON CONFLICT ({conflict}) DO NOTHING"
    assignments = ", ".join(
        f"{column} = excluded.{column}" for column in columns if column not in conflict_columns
    )
    return statement + f" ON CONFLICT ({conflict}) DO UPDATE SET {assignments}"


_SETTINGS_UPSERT = _insert_sql("user_settings", SETTINGS_COLUMNS, ("user_id",), True)
_SETTINGS_LEGACY_INSERT = _insert_sql("user_settings", SETTINGS_COLUMNS, ("user_id",), False)
_WORKSPACE_UPSERT = _insert_sql(
    "workspaces", WORKSPACE_COLUMNS, ("user_id", "session_name"), True
)
_WORKSPACE_LEGACY_INSERT = _insert_sql(
    "workspaces", WORKSPACE_COLUMNS, ("user_id", "session_name"), False
)
_CHAT_INSERT = _insert_sql("ai_chat_history", CHAT_COLUMNS, (), False)
_ALGOLAB_UPSERT = _insert_sql("algolab_state", ALGOLAB_COLUMNS, ("user_id",), True)
_ALGOLAB_LEGACY_INSERT = _insert_sql("algolab_state", ALGOLAB_COLUMNS, ("user_id",), False)

SCHEMA_STATEMENTS: Tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS user_settings (
        id BIGSERIAL PRIMARY KEY,
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
        id BIGSERIAL PRIMARY KEY,
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
        id BIGSERIAL PRIMARY KEY,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        skill TEXT,
        agent_actions TEXT,
        timestamp TEXT DEFAULT (now()::text)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS algolab_state (
        id BIGSERIAL PRIMARY KEY,
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
    CREATE TABLE IF NOT EXISTS migration_state (
        name TEXT PRIMARY KEY,
        applied_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_settings_user_id ON user_settings (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_workspaces_user_id ON workspaces (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_ai_chat_history_user_id ON ai_chat_history (user_id)",
    "CREATE INDEX IF NOT EXISTS idx_algolab_state_user_id ON algolab_state (user_id)",
    "ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS extra_settings TEXT DEFAULT '{}'",
    "ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS risk_max_daily_loss REAL DEFAULT 500.0",
    "ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS risk_max_contracts INTEGER DEFAULT 1",
    "ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS risk_emotional_guard INTEGER DEFAULT 0",
    "ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS risk_locked_until TEXT",
    "ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS show_dom INTEGER DEFAULT 0",
    "ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS chart_settings TEXT DEFAULT '{}'",
    "ALTER TABLE algolab_state ADD COLUMN IF NOT EXISTS is_chat_open INTEGER DEFAULT 0",
    "ALTER TABLE algolab_state ADD COLUMN IF NOT EXISTS chat_width INTEGER DEFAULT 350",
)


def _flag(value: Any) -> bool:
    return bool(value)


def _stored_flag(value: Any) -> int:
    return 1 if value else 0


def _settings_row(row: Dict[str, Any]) -> Dict[str, Any]:
    settings: Dict[str, Any] = {}
    for column in SETTINGS_COLUMNS:
        if column in ("user_id", "updated_at"):
            continue
        value = row.get(column, _SETTINGS_DEFAULTS.get(column))
        settings[column] = _flag(value) if column in _BOOLEAN_SETTINGS else value
    settings["updated_at"] = row.get("updated_at")
    return settings


def _workspace_row(row: Dict[str, Any], *, detail: bool) -> Dict[str, Any]:
    panel_sizes = json.loads(row["panel_sizes"]) if row.get("panel_sizes") else {}
    workspace: Dict[str, Any] = {
        "layout": row.get("layout"),
        "charts": json.loads(row["charts"]) if row.get("charts") else [],
        "active_chart_id": row.get("active_chart_id"),
        "symbol": row.get("symbol"),
        "timeframe": row.get("timeframe"),
        "show_tape": _flag(row.get("show_tape")),
        "show_order_entry": _flag(row.get("show_order_entry")),
        "drawings": json.loads(row["drawings"]) if row.get("drawings") else [],
        "panel_sizes": panel_sizes,
        "symbol_settings": json.loads(row["symbol_settings"]) if row.get("symbol_settings") else {},
        "indicator_settings": json.loads(row["indicator_settings"]) if row.get("indicator_settings") else {},
        "visibility_settings": json.loads(row["visibility_settings"]) if row.get("visibility_settings") else {},
        "show_dom": _flag(row.get("show_dom")),
        "chart_settings": json.loads(row["chart_settings"]) if row.get("chart_settings") else {},
        "updated_at": row.get("updated_at"),
    }
    if detail:
        workspace["session_name"] = row.get("session_name")
        workspace["tapeWidth"] = panel_sizes.get("tapeWidth")
        workspace["orderEntryWidth"] = panel_sizes.get("orderEntryWidth")
        workspace["domWidth"] = panel_sizes.get("domWidth")
        workspace["tape1Height"] = panel_sizes.get("tape1Height")
        workspace["tape2Height"] = panel_sizes.get("tape2Height")
    else:
        # The list projection keeps its historical shape (no show_dom key).
        workspace.pop("show_dom")
    return workspace


class PostgresUserRepository:
    """Tenant-scoped storage operations. One instance per database URL."""

    def __init__(self, url: str):
        if not url:
            raise DatabaseNotConfigured("A PostgreSQL connection string is required")
        self.url = url

    @contextmanager
    def _cursor(self):
        connection, cursor_factory = _open_connection(self.url)
        cursor = connection.cursor(cursor_factory=cursor_factory)
        try:
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
            for statement in SCHEMA_STATEMENTS:
                cursor.execute(statement)

    # ── settings ──────────────────────────────────────────────────

    def get_settings(self, user_id: str) -> Dict[str, Any]:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT * FROM user_settings WHERE user_id = %(user_id)s",
                {"user_id": user_id},
            )
            row = cursor.fetchone()
        return _settings_row(row) if row else dict(_SETTINGS_DEFAULTS)

    def save_settings(self, user_id: str, data: Dict[str, Any]) -> bool:
        current = self.get_settings(user_id)
        values: Dict[str, Any] = {"user_id": user_id}
        for column in SETTINGS_COLUMNS[1:]:
            if column == "updated_at":
                continue
            value = data.get(column, current.get(column, _SETTINGS_DEFAULTS.get(column)))
            values[column] = _stored_flag(value) if column in _BOOLEAN_SETTINGS else value
        values["updated_at"] = datetime.now().isoformat()
        with self._cursor() as cursor:
            cursor.execute(_SETTINGS_UPSERT, values)
        return True

    # ── workspaces ────────────────────────────────────────────────

    def get_workspace(self, user_id: str, session_name: str) -> Optional[Dict[str, Any]]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM workspaces
                WHERE user_id = %(user_id)s AND session_name = %(session_name)s
                """,
                {"user_id": user_id, "session_name": session_name},
            )
            row = cursor.fetchone()
        return _workspace_row(row, detail=True) if row else None

    def save_workspace(self, user_id: str, session_name: str, data: Dict[str, Any]) -> bool:
        values: Dict[str, Any] = {
            "user_id": user_id,
            "session_name": session_name,
            "layout": data.get("layout", "single"),
            "charts": json.dumps(data.get("charts", [])),
            "active_chart_id": data.get("active_chart_id", 1),
            "symbol": data.get("symbol", "MNQ"),
            "timeframe": data.get("timeframe", "1m"),
            "show_tape": _stored_flag(data.get("show_tape", True)),
            "show_order_entry": _stored_flag(data.get("show_order_entry", True)),
            "drawings": json.dumps(data.get("drawings", [])),
            "panel_sizes": json.dumps(data.get("panel_sizes", {})),
            "symbol_settings": json.dumps(data.get("symbol_settings", {})),
            "indicator_settings": json.dumps(data.get("indicator_settings", {})),
            "visibility_settings": json.dumps(data.get("visibility_settings", {})),
            "show_dom": _stored_flag(data.get("show_dom", False) or data.get("showDom", False)),
            "chart_settings": json.dumps(data.get("chart_settings", {})),
            "updated_at": datetime.now().isoformat(),
        }
        with self._cursor() as cursor:
            cursor.execute(_WORKSPACE_UPSERT, values)
        return True

    def get_all_workspaces(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT * FROM workspaces WHERE user_id = %(user_id)s",
                {"user_id": user_id},
            )
            rows = cursor.fetchall()
        return {
            row["session_name"]: _workspace_row(row, detail=False)
            for row in rows
        }

    def delete_workspace(self, user_id: str, session_name: str) -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM workspaces
                WHERE user_id = %(user_id)s AND session_name = %(session_name)s
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
                VALUES (%(user_id)s, %(last_active_workspace)s, %(updated_at)s)
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
            cursor.execute(
                """
                SELECT * FROM ai_chat_history
                WHERE user_id = %(user_id)s
                ORDER BY id ASC
                LIMIT %(limit)s
                """,
                {"user_id": user_id, "limit": limit},
            )
            rows = cursor.fetchall()
        return [
            {
                "role": row["role"],
                "content": row["content"],
                "skill": row.get("skill"),
                "agent_actions": json.loads(row["agent_actions"]) if row.get("agent_actions") else None,
                "timestamp": row.get("timestamp"),
            }
            for row in rows
        ]

    def save_ai_chat_message(
        self,
        user_id: str,
        role: str,
        content: str,
        skill: Optional[str] = None,
        agent_actions: Optional[Dict[str, Any]] = None,
    ) -> None:
        values = {
            "user_id": user_id,
            "role": role,
            "content": content,
            "skill": skill,
            "agent_actions": json.dumps(agent_actions) if agent_actions else None,
        }
        with self._cursor() as cursor:
            cursor.execute(_CHAT_INSERT, values)

    def clear_ai_chat_history(self, user_id: str) -> None:
        with self._cursor() as cursor:
            cursor.execute(
                "DELETE FROM ai_chat_history WHERE user_id = %(user_id)s",
                {"user_id": user_id},
            )

    # ── algolab state ─────────────────────────────────────────────

    def get_algolab_state(self, user_id: str) -> Dict[str, Any]:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT * FROM algolab_state WHERE user_id = %(user_id)s",
                {"user_id": user_id},
            )
            row = cursor.fetchone()
        if not row:
            return {
                "open_files": [],
                "file_contents": {},
                "active_file_path": None,
                "is_chat_open": False,
                "chat_width": 350,
            }
        return {
            "open_files": json.loads(row["open_files"]) if row.get("open_files") else [],
            "file_contents": json.loads(row["file_contents"]) if row.get("file_contents") else {},
            "active_file_path": row.get("active_file_path"),
            "is_chat_open": _flag(row.get("is_chat_open")),
            "chat_width": row.get("chat_width") or 350,
        }

    def save_algolab_state(self, user_id: str, state: Dict[str, Any]) -> None:
        values = {
            "user_id": user_id,
            "open_files": json.dumps(state.get("open_files", [])),
            "file_contents": json.dumps(state.get("file_contents", {})),
            "active_file_path": state.get("active_file_path"),
            "is_chat_open": _stored_flag(state.get("is_chat_open")),
            "chat_width": state.get("chat_width", 350),
            "updated_at": datetime.now().isoformat(),
        }
        with self._cursor() as cursor:
            cursor.execute(_ALGOLAB_UPSERT, values)

    # ── legacy SQLite compatibility import ────────────────────────

    def clear_legacy_import_marker(self, marker: str = LEGACY_IMPORT_MARKER) -> None:
        """Drop the marker so a deliberate re-import can run once more."""
        connection, cursor_factory = _open_connection(self.url)
        try:
            cursor = connection.cursor(cursor_factory=cursor_factory)
            cursor.execute(
                "DELETE FROM migration_state WHERE name = %(name)s",
                {"name": marker},
            )
            connection.commit()
        finally:
            connection.close()

    def delete_user_rows(self, user_id: str) -> Dict[str, int]:
        """Remove one tenant's rows before a deliberate replace import."""
        if not user_id:
            raise ValueError("user_id is required")
        removed: Dict[str, int] = {}
        connection, cursor_factory = _open_connection(self.url)
        try:
            cursor = connection.cursor(cursor_factory=cursor_factory)
            for table in ("ai_chat_history", "workspaces", "algolab_state", "user_settings"):
                cursor.execute(
                    f"DELETE FROM {table} WHERE user_id = %(user_id)s",
                    {"user_id": user_id},
                )
                removed[table] = cursor.rowcount
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return removed

    def legacy_import_applied(self, marker: str = LEGACY_IMPORT_MARKER) -> bool:
        """True when the one-time import marker is already recorded."""
        connection, cursor_factory = _open_connection(self.url)
        try:
            cursor = connection.cursor(cursor_factory=cursor_factory)
            cursor.execute(
                "SELECT 1 FROM migration_state WHERE name = %(name)s",
                {"name": marker},
            )
            return cursor.fetchone() is not None
        finally:
            connection.close()

    def import_legacy_sqlite(
        self, sqlite_path: Optional[str], marker: str = LEGACY_IMPORT_MARKER
    ) -> Dict[str, Any]:
        """Copy pre-migration SQLite rows into Postgres under ``default_user`` once.

        The marker insert and every row insert share one transaction, so a partial
        import is rolled back and a repeat run is a no-op. Existing Postgres rows
        are never overwritten (``DO NOTHING``).
        """
        if (os.environ.get(LEGACY_IMPORT_DISABLE_ENV) or "").strip().lower() in {
            "1", "true", "yes", "on",
        }:
            return {"status": "disabled", "imported": {}}
        if not sqlite_path or not os.path.exists(sqlite_path):
            return {"status": "skipped_missing_file", "imported": {}}
        legacy = _read_legacy_rows(sqlite_path)
        if legacy is None:
            return {"status": "skipped_unreadable_file", "imported": {}}

        imported = {table: 0 for table in legacy}
        connection, cursor_factory = _open_connection(self.url)
        try:
            cursor = connection.cursor(cursor_factory=cursor_factory)
            cursor.execute(
                """
                INSERT INTO migration_state (name, applied_at)
                VALUES (%(name)s, %(applied_at)s)
                ON CONFLICT (name) DO NOTHING
                """,
                {"name": marker, "applied_at": datetime.now().isoformat()},
            )
            if cursor.rowcount == 0:
                connection.rollback()
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
                    values = _legacy_values(row, columns, defaults)
                    cursor.execute(statement, values)
                    imported[table] += cursor.rowcount
            for row in legacy.get("ai_chat_history", []):
                values = _legacy_values(
                    row, CHAT_COLUMNS, {"skill": None, "agent_actions": None}
                )
                if not values.get("content"):
                    continue
                cursor.execute(_CHAT_INSERT, values)
                imported["ai_chat_history"] += cursor.rowcount
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return {"status": "applied", "imported": imported}


def _legacy_values(
    row: Dict[str, Any], columns: Tuple[str, ...], defaults: Dict[str, Any]
) -> Dict[str, Any]:
    """Map a legacy row onto target columns, forcing the compatibility tenant id."""
    values: Dict[str, Any] = {}
    for column in columns:
        if column == "user_id":
            values[column] = DEFAULT_USER_ID
            continue
        values[column] = row[column] if column in row else defaults.get(column)
    return values


def _read_legacy_rows(path: str) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    """Read legacy tables read-only; ``None`` means the file is not a usable store."""
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except sqlite3.Error:
            return None
        rows: Dict[str, List[Dict[str, Any]]] = {}
        identity = legacy_import_user_id()
        for table in ("user_settings", "workspaces", "ai_chat_history", "algolab_state"):
            try:
                found = [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
            except sqlite3.Error:
                found = []
            for row in found:
                row["user_id"] = identity
            rows[table] = found
        return rows
    finally:
        connection.close()


_repository: Optional[PostgresUserRepository] = None


def get_repository() -> PostgresUserRepository:
    """Return the process repository, created from ``DATABASE_URL`` on first use."""
    global _repository
    if _repository is None:
        _repository = PostgresUserRepository(database_url())
    return _repository


def set_repository(repository: Optional[PostgresUserRepository]) -> None:
    """Install a repository (tests and operational overrides)."""
    global _repository
    _repository = repository


def reset_repository() -> None:
    global _repository
    _repository = None
