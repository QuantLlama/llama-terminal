"""Postgres-backed per-user storage contract, exercised against a fake driver.

No test here contacts a real database: ``FakePostgres`` records the SQL text and
bound parameters that the repository emits and answers the small, uniform set of
statements the repository issues. That keeps the assertions on real SQL shape
(parameterized placeholders, tenant filters, upsert conflict keys) while the
suite stays offline and hermetic.
"""
import os
import re
import sqlite3
from pathlib import Path

import pytest

from src.services import user_repository
from src.services.user_repository import (
    DEFAULT_USER_ID,
    LEGACY_IMPORT_DISABLE_ENV,
    DatabaseNotConfigured,
    PostgresUserRepository,
)

ROOT = Path(__file__).resolve().parents[1]

CREATE_TABLE_RE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-z_]+)", re.I)
CREATE_INDEX_RE = re.compile(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?\w+\s+ON\s+([a-z_]+)", re.I)
INSERT_RE = re.compile(r"INSERT\s+INTO\s+([a-z_]+)", re.I)
SELECT_RE = re.compile(r"FROM\s+([a-z_]+)", re.I)
UPDATE_RE = re.compile(r"UPDATE\s+([a-z_]+)", re.I)
DELETE_RE = re.compile(r"DELETE\s+FROM\s+([a-z_]+)", re.I)
CONFLICT_RE = re.compile(r"ON\s+CONFLICT\s*\(([^)]+)\)", re.I)
SET_RE = re.compile(r"\bSET\s+(.*?)\s+WHERE\b", re.I | re.S)
ASSIGN_RE = re.compile(r"([a-z_]+)\s*=\s*%\((\w+)\)s", re.I)


class FakePostgres:
    """Minimal single-table SQL store used as a stand-in for a Postgres server."""

    def __init__(self):
        self.tables = {}
        self.statements = []
        self.connection_urls = []
        self._ids = {}

    def record(self, sql, params):
        self.statements.append((sql, params))

    def rows(self, table):
        return self.tables.setdefault(table, [])

    def next_id(self, table):
        self._ids[table] = self._ids.get(table, 0) + 1
        return self._ids[table]

    def snapshot(self):
        return {name: [dict(row) for row in rows] for name, rows in self.tables.items()}


class FakeCursor:
    def __init__(self, store):
        self.store = store
        self.rowcount = 0
        self._rows = []

    def execute(self, sql, params=None):
        self.store.record(sql, params)
        self.rowcount = 0
        self._rows = []
        upper = sql.strip().upper()
        if upper.startswith("CREATE"):
            table = CREATE_TABLE_RE.search(sql) or CREATE_INDEX_RE.search(sql)
            if table:
                self.store.rows(table.group(1).lower())
            return
        if upper.startswith("ALTER"):
            return
        if upper.startswith("INSERT"):
            return self._insert(sql, dict(params or {}))
        if upper.startswith("SELECT"):
            return self._select(sql, dict(params or {}))
        if upper.startswith("UPDATE"):
            return self._update(sql, dict(params or {}))
        if upper.startswith("DELETE"):
            return self._delete(sql, dict(params or {}))
        raise AssertionError(f"FakePostgres cannot interpret SQL: {sql}")

    def _insert(self, sql, values):
        table = INSERT_RE.search(sql).group(1).lower()
        rows = self.store.rows(table)
        conflict = CONFLICT_RE.search(sql)
        do_nothing = "DO NOTHING" in sql.upper()
        if conflict:
            keys = [key.strip() for key in conflict.group(1).split(",")]
            matches = [row for row in rows if all(row.get(key) == values.get(key) for key in keys)]
            if matches:
                if do_nothing:
                    return
                for row in matches:
                    row.update(values)
                self.rowcount = len(matches)
                return
        values.setdefault("id", self.store.next_id(table))
        rows.append(values)
        self.rowcount = 1

    def _filtered(self, table, params):
        rows = self.store.rows(table)
        if not rows:
            return []
        columns = set(rows[0])
        filters = {key: value for key, value in params.items() if key in columns}
        return [row for row in rows if all(row.get(key) == value for key, value in filters.items())]

    def _select(self, sql, params):
        table = SELECT_RE.search(sql).group(1).lower()
        matched = self._filtered(table, params)
        if "ORDER BY ID" in sql.upper():
            matched = sorted(matched, key=lambda row: row.get("id", 0))
        limit = params.get("limit")
        if isinstance(limit, int):
            matched = matched[:limit]
        self._rows = [dict(row) for row in matched]

    def _update(self, sql, params):
        table = UPDATE_RE.search(sql).group(1).lower()
        assignments = ASSIGN_RE.findall(SET_RE.search(sql).group(1))
        assigned = {column for column, _ in assignments}
        filters = {key: value for key, value in params.items() if key not in assigned}
        matched = self._filtered(table, filters)
        for row in matched:
            for column, placeholder in assignments:
                row[column] = params[placeholder]
        self.rowcount = len(matched)

    def _delete(self, sql, params):
        table = DELETE_RE.search(sql).group(1).lower()
        rows = self.store.rows(table)
        matched = self._filtered(table, params)
        for row in matched:
            rows.remove(row)
        self.rowcount = len(matched)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConnection:
    def __init__(self, store):
        self.store = store
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, cursor_factory=None):
        return FakeCursor(self.store)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


def open_fake_connection(store):
    def _open(url):
        store.connection_urls.append(url)
        return FakeConnection(store), None

    return _open


@pytest.fixture
def store(monkeypatch):
    fake = FakePostgres()
    monkeypatch.setattr(user_repository, "_open_connection", open_fake_connection(fake))
    return fake


@pytest.fixture
def repo(store):
    repository = PostgresUserRepository("postgresql://synthetic.invalid/per_user")
    repository.ensure_schema()
    return repository


def statements_for(store, verb):
    return [
        (sql, params)
        for sql, params in store.statements
        if sql.strip().upper().startswith(verb)
    ]


# ── configuration boundary ─────────────────────────────────────────


def test_storage_requires_database_url_instead_of_falling_back_to_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    user_repository.reset_repository()
    with pytest.raises(DatabaseNotConfigured) as excinfo:
        user_repository.get_repository()
    assert "DATABASE_URL" in str(excinfo.value)
    assert "sqlite" in str(excinfo.value).lower()


def test_facade_rejects_database_url_absence_loudly(monkeypatch):
    from src.services import database

    monkeypatch.delenv("DATABASE_URL", raising=False)
    user_repository.reset_repository()
    with pytest.raises(DatabaseNotConfigured):
        database.get_settings(user_id="user-a")


def test_repository_is_only_created_from_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://synthetic.invalid/app")
    user_repository.reset_repository()
    repository = user_repository.get_repository()
    assert repository.url == "postgresql://synthetic.invalid/app"
    user_repository.reset_repository()


# ── schema ─────────────────────────────────────────────────────────


def test_schema_declares_tenant_columns_and_keys(store, repo):
    ddl = "\n".join(sql for sql, _ in store.statements)
    assert "CREATE TABLE IF NOT EXISTS user_settings" in ddl
    assert "CREATE TABLE IF NOT EXISTS workspaces" in ddl
    assert "CREATE TABLE IF NOT EXISTS ai_chat_history" in ddl
    assert "CREATE TABLE IF NOT EXISTS algolab_state" in ddl
    assert ddl.count("user_id TEXT NOT NULL") >= 4
    assert "UNIQUE (user_id, session_name)" in ddl
    assert "UNIQUE (user_id)" in ddl
    assert "CREATE INDEX IF NOT EXISTS idx_workspaces_user_id ON workspaces (user_id)" in ddl
    assert "DEFAULT 'default_user'" not in ddl
    assert "default_user" not in ddl


def test_schema_creation_is_idempotent(store, repo):
    first_run = len(store.statements)
    repo.ensure_schema()
    repo.ensure_schema()
    statements = store.statements[first_run:]
    assert statements
    assert all(sql.strip().upper().startswith(("CREATE", "ALTER")) for sql, _ in statements)
    assert len(statements) == 2 * first_run
    assert all(params is None for _, params in statements)


# ── parameterization ───────────────────────────────────────────────


def test_every_statement_binds_tenant_ids_instead_of_interpolating(store, repo):
    repo.save_settings("user-a", {"theme": "dark"})
    repo.get_settings("user-a")
    repo.save_workspace("user-a", "alpha", {"layout": "grid"})
    repo.get_workspace("user-a", "alpha")
    repo.get_all_workspaces("user-a")
    repo.delete_workspace("user-a", "alpha")
    repo.save_ai_chat_message("user-a", "user", "hello")
    repo.get_ai_chat_history("user-a")
    repo.clear_ai_chat_history("user-a")
    repo.save_algolab_state("user-a", {"open_files": []})
    repo.get_algolab_state("user-a")
    repo.set_last_active_workspace("user-a", "alpha")

    tenant_statements = [
        (sql, params) for sql, params in store.statements
        if "user-a" in str(params) or "user-a" in sql
    ]
    assert tenant_statements
    for sql, params in tenant_statements:
        assert "user-a" not in sql, sql
        assert isinstance(params, dict) and params.get("user_id") == "user-a", sql
        assert "%(user_id)s" in sql


def test_no_repository_statement_mentions_the_default_user(store, repo):
    repo.get_settings("user-a")
    repo.save_settings("user-a", {"theme": "dark"})
    repo.get_workspace("user-a", "alpha")
    repo.save_workspace("user-a", "alpha", {})
    repo.get_all_workspaces("user-a")
    repo.delete_workspace("user-a", "alpha")
    repo.get_algolab_state("user-a")
    repo.save_algolab_state("user-a", {})
    repo.get_ai_chat_history("user-a")
    repo.save_ai_chat_message("user-a", "user", "hi")
    repo.clear_ai_chat_history("user-a")

    for sql, params in store.statements:
        assert DEFAULT_USER_ID not in sql
        assert DEFAULT_USER_ID not in str(params)


# ── per-user behaviour ─────────────────────────────────────────────


def test_settings_upsert_keeps_users_independent(repo, store):
    assert repo.save_settings("user-a", {"theme": "dark", "show_grid": False}) is True
    repo.save_settings("user-b", {"theme": "light"})

    assert repo.get_settings("user-a")["theme"] == "dark"
    assert repo.get_settings("user-a")["show_grid"] is False
    assert repo.get_settings("user-b")["theme"] == "light"

    repo.save_settings("user-b", {"theme": "midnight"})
    assert repo.get_settings("user-a")["theme"] == "dark"
    assert repo.get_settings("user-b")["theme"] == "midnight"

    rows = {row["user_id"]: row for row in store.rows("user_settings")}
    assert set(rows) == {"user-a", "user-b"}


def test_unknown_user_reads_private_empty_defaults(repo):
    settings = repo.get_settings("nobody")
    assert settings["theme"] == "dark"
    assert settings["last_active_workspace"] == "session_mt5"
    assert repo.get_all_workspaces("nobody") == {}
    assert repo.get_ai_chat_history("nobody") == []
    assert repo.get_algolab_state("nobody")["open_files"] == []
    assert repo.get_workspace("nobody", "alpha") is None


def test_workspaces_are_scoped_per_user(repo, store):
    repo.save_workspace("user-a", "alpha", {"layout": "grid", "symbol": "MNQ"})
    repo.save_workspace("user-b", "alpha", {"layout": "single", "symbol": "ES"})

    assert repo.get_workspace("user-a", "alpha")["layout"] == "grid"
    assert repo.get_workspace("user-b", "alpha")["layout"] == "single"
    assert set(repo.get_all_workspaces("user-a")) == {"alpha"}
    assert repo.get_workspace("user-a", "alpha")["symbol"] == "MNQ"

    rows = store.rows("workspaces")
    assert {(row["user_id"], row["session_name"]) for row in rows} == {
        ("user-a", "alpha"), ("user-b", "alpha")
    }


def test_delete_workspace_never_crosses_tenant_boundary(repo, store):
    repo.save_workspace("user-b", "alpha", {"layout": "single"})

    assert repo.delete_workspace("user-a", "alpha") is False
    assert repo.get_workspace("user-b", "alpha") is not None
    assert repo.delete_workspace("user-b", "alpha") is True
    assert repo.get_workspace("user-b", "alpha") is None
    assert store.rows("workspaces") == []


def test_chat_history_is_scoped_per_user(repo):
    repo.save_ai_chat_message("user-a", "user", "from-a")
    repo.save_ai_chat_message("user-b", "user", "from-b")
    repo.save_ai_chat_message("user-b", "assistant", "b-answer")

    assert [row["content"] for row in repo.get_ai_chat_history("user-a")] == ["from-a"]
    assert [row["content"] for row in repo.get_ai_chat_history("user-b")] == ["from-b", "b-answer"]

    repo.clear_ai_chat_history("user-a")
    assert repo.get_ai_chat_history("user-a") == []
    assert len(repo.get_ai_chat_history("user-b")) == 2


def test_algolab_state_is_scoped_per_user(repo):
    repo.save_algolab_state("user-a", {
        "open_files": [{"path": "a.py"}], "file_contents": {"a.py": "print('a')"},
        "active_file_path": "a.py", "is_chat_open": True, "chat_width": 500,
    })
    repo.save_algolab_state("user-b", {"open_files": [], "file_contents": {}})

    state_a = repo.get_algolab_state("user-a")
    state_b = repo.get_algolab_state("user-b")
    assert state_a["active_file_path"] == "a.py"
    assert state_a["file_contents"] == {"a.py": "print('a')"}
    assert state_a["is_chat_open"] is True
    assert state_a["chat_width"] == 500
    assert state_b["open_files"] == []
    assert state_b["active_file_path"] is None


def test_last_active_workspace_is_scoped_per_user(repo):
    repo.save_settings("user-a", {})
    repo.save_settings("user-b", {})
    assert repo.set_last_active_workspace("user-a", "alpha") is True
    repo.set_last_active_workspace("user-b", "beta")

    assert repo.get_last_active_workspace("user-a") == "alpha"
    assert repo.get_last_active_workspace("user-b") == "beta"

    # A tenant with no row yet gains only its own row.
    assert repo.set_last_active_workspace("user-c", "gamma") is True
    assert repo.get_last_active_workspace("user-c") == "gamma"
    assert repo.get_settings("user-a")["last_active_workspace"] == "alpha"


# ── legacy SQLite compatibility import ─────────────────────────────


def legacy_sqlite(path):
    """Create a synthetic pre-migration SQLite file (never a real credential store)."""
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE user_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default_user' UNIQUE,
            platform TEXT DEFAULT 'mt5',
            theme TEXT DEFAULT 'dark',
            show_grid INTEGER DEFAULT 1
        );
        CREATE TABLE workspaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default_user',
            session_name TEXT NOT NULL,
            layout TEXT DEFAULT 'single',
            symbol TEXT DEFAULT 'MNQ',
            UNIQUE(user_id, session_name)
        );
        CREATE TABLE ai_chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default_user',
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            skill TEXT,
            agent_actions TEXT
        );
        CREATE TABLE algolab_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default_user' UNIQUE,
            open_files TEXT DEFAULT '[]',
            file_contents TEXT DEFAULT '{}',
            active_file_path TEXT,
            is_chat_open INTEGER DEFAULT 0,
            chat_width INTEGER DEFAULT 350
        );
        """
    )
    connection.execute(
        "INSERT INTO user_settings (user_id, platform, theme) VALUES ('default_user', 'mt5', 'legacy')"
    )
    connection.execute(
        "INSERT INTO workspaces (user_id, session_name, layout, symbol) VALUES ('default_user', 'legacy_ws', 'grid', 'MNQ')"
    )
    connection.execute(
        "INSERT INTO ai_chat_history (user_id, role, content) VALUES ('default_user', 'user', 'legacy-message')"
    )
    connection.execute(
        "INSERT INTO algolab_state (user_id, open_files, active_file_path) VALUES ('default_user', '[]', 'legacy.py')"
    )
    connection.commit()
    connection.close()
    return str(path)


def test_legacy_import_maps_rows_to_default_user_once(repo, store, tmp_path):
    source = legacy_sqlite(tmp_path / "quantum_llama.db")

    first = repo.import_legacy_sqlite(source)
    assert first["status"] == "applied"
    assert first["imported"] == {
        "user_settings": 1, "workspaces": 1,
        "ai_chat_history": 1, "algolab_state": 1,
    }
    assert {row["user_id"] for row in store.rows("user_settings")} == {DEFAULT_USER_ID}
    assert store.rows("workspaces")[0]["session_name"] == "legacy_ws"
    assert store.rows("ai_chat_history")[0]["content"] == "legacy-message"

    rows_before = store.snapshot()
    second = repo.import_legacy_sqlite(source)
    assert second["status"] == "skipped_already_applied"
    assert store.snapshot() == rows_before


def test_legacy_import_never_overwrites_existing_postgres_rows(repo, store, tmp_path):
    repo.save_settings(DEFAULT_USER_ID, {"theme": "postgres-wins"})
    source = legacy_sqlite(tmp_path / "quantum_llama.db")

    assert repo.import_legacy_sqlite(source)["status"] == "applied"
    assert repo.get_settings(DEFAULT_USER_ID)["theme"] == "postgres-wins"


def test_legacy_import_skips_missing_or_unreadable_file(repo, store, tmp_path):
    missing = tmp_path / "absent.db"
    assert repo.import_legacy_sqlite(str(missing))["status"] == "skipped_missing_file"
    assert store.rows("user_settings") == []

    unreadable = tmp_path / "unreadable.db"
    unreadable.write_text("not a sqlite database")
    result = repo.import_legacy_sqlite(str(unreadable))
    assert result["status"] == "skipped_unreadable_file"
    assert store.rows("user_settings") == []


def test_legacy_import_can_be_disabled_by_the_operator(repo, store, tmp_path, monkeypatch):
    source = legacy_sqlite(tmp_path / "quantum_llama.db")
    monkeypatch.setenv(LEGACY_IMPORT_DISABLE_ENV, "1")

    assert repo.import_legacy_sqlite(source)["status"] == "disabled"
    assert all(rows == [] for rows in store.tables.values())


def test_legacy_import_does_not_read_the_repository_worktree_file(monkeypatch, store, tmp_path):
    from src.services import database

    missing = tmp_path / "data" / "quantum_llama.db"
    monkeypatch.setattr(database, "get_db_path", lambda: str(missing))
    repository = PostgresUserRepository("postgresql://synthetic.invalid/per_user")

    assert repository.import_legacy_sqlite(database.get_db_path())["status"] == "skipped_missing_file"
    assert not os.path.exists(str(missing))
