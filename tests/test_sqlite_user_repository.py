"""SQLite backend contract: same behaviour as Postgres, opt-in, local only.

Every assertion goes through the public repository interface. The parity test
runs one scenario twice - against ``PostgresUserRepository`` on the fake DB-API
driver from ``test_database_postgres`` and against a real SQLite file - and
compares every returned value, so "the same contract" is measured instead of
claimed. Isolation, backend selection and the cloud-to-local copy are then
asserted separately, one rule per test.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

from src.services import database, user_repository
from src.services.sqlite_user_repository import SqliteUserRepository
from src.services.user_repository import (
    DatabaseNotConfigured,
    PostgresUserRepository,
)
from test_database_postgres import FakePostgres, open_fake_connection

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "migrate_cloud_to_sqlite", ROOT / "scripts/migrate_cloud_to_sqlite.py"
)
migration = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = migration
SPEC.loader.exec_module(migration)

STORAGE_ENV = "QLLAMA_STORAGE"
SQLITE_PATH_ENV = "QLLAMA_SQLITE_PATH"
DEFAULT_SQLITE_PATH = ROOT / "config" / "quantum_llama.db"

# Timestamps are produced per store by clock and default, never by the contract.
TIME_KEYS = {"timestamp", "updated_at", "created_at"}


def _drop_times(value):
    if isinstance(value, dict):
        return {key: _drop_times(item) for key, item in value.items() if key not in TIME_KEYS}
    if isinstance(value, list):
        return [_drop_times(item) for item in value]
    return value


# ── fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def sqlite_repo(tmp_path):
    repository = SqliteUserRepository(str(tmp_path / "quantum_llama.db"))
    repository.ensure_schema()
    return repository


@pytest.fixture
def postgres_repo(monkeypatch):
    store = FakePostgres()
    monkeypatch.setattr(user_repository, "_open_connection", open_fake_connection(store))
    repository = PostgresUserRepository("postgresql://synthetic.invalid/per_user")
    repository.ensure_schema()
    return repository


@pytest.fixture(autouse=True)
def clean_process_repository():
    user_repository.reset_repository()
    yield
    user_repository.reset_repository()


# ── the full contract, measured against Postgres ───────────────────


def _run_contract(repository):
    """Exercise every public read/write of the contract once, in order."""
    results = {}

    results["settings_defaults"] = repository.get_settings("user-a")
    results["save_settings"] = repository.save_settings(
        "user-a",
        {"theme": "light", "show_grid": False, "risk_max_daily_loss": 250.0},
    )
    results["settings_after_save"] = repository.get_settings("user-a")
    results["settings_unknown_user"] = repository.get_settings("user-nobody")

    results["save_workspace"] = repository.save_workspace(
        "user-a",
        "alpha",
        {
            "layout": "grid",
            "charts": [{"id": 1, "symbol": "ES"}],
            "symbol": "ES",
            "show_dom": True,
            "panel_sizes": {"tapeWidth": 320},
        },
    )
    results["get_workspace"] = repository.get_workspace("user-a", "alpha")
    results["missing_workspace"] = repository.get_workspace("user-a", "absent")
    repository.save_workspace("user-a", "beta", {"layout": "single"})
    results["all_workspaces"] = repository.get_all_workspaces("user-a")

    results["last_active_default"] = repository.get_last_active_workspace("user-a")
    results["set_last_active"] = repository.set_last_active_workspace("user-a", "beta")
    results["last_active"] = repository.get_last_active_workspace("user-a")

    results["delete_workspace"] = repository.delete_workspace("user-a", "beta")
    results["delete_workspace_again"] = repository.delete_workspace("user-a", "beta")

    results["chat_empty"] = repository.get_ai_chat_history("user-a")
    repository.save_ai_chat_message("user-a", "user", "hello")
    repository.save_ai_chat_message(
        "user-a", "assistant", "answer", skill="algolab", agent_actions={"steps": [1]}
    )
    results["chat"] = repository.get_ai_chat_history("user-a")
    results["chat_limit"] = repository.get_ai_chat_history("user-a", limit=1)
    results["clear_chat"] = repository.clear_ai_chat_history("user-a")
    results["chat_after_clear"] = repository.get_ai_chat_history("user-a")

    results["algolab_default"] = repository.get_algolab_state("user-a")
    repository.save_algolab_state(
        "user-a",
        {
            "open_files": [{"path": "a.py"}],
            "file_contents": {"a.py": "print('a')"},
            "active_file_path": "a.py",
            "is_chat_open": True,
            "chat_width": 500,
        },
    )
    results["algolab"] = repository.get_algolab_state("user-a")

    results["accounts_empty"] = repository.list_accounts(user_id="user-a")
    results["upsert_account"] = repository.upsert_account(
        user_id="user-a",
        platform="mt5",
        account_id="a1",
        metadata={"name": "A", "nested": {"k": 1}},
        credential_blob="blob-a",
    )
    results["get_account"] = repository.get_account(
        user_id="user-a", platform="mt5", account_id="a1"
    )
    results["list_accounts"] = repository.list_accounts(user_id="user-a")
    results["missing_account"] = repository.get_account(
        user_id="user-a", platform="mt5", account_id="absent"
    )
    results["delete_account"] = repository.delete_account(
        user_id="user-a", platform="mt5", account_id="a1"
    )
    results["delete_account_again"] = repository.delete_account(
        user_id="user-a", platform="mt5", account_id="a1"
    )
    return results


def test_every_contract_call_returns_what_the_postgres_repository_returns(
    postgres_repo, sqlite_repo
):
    postgres = _drop_times(_run_contract(postgres_repo))
    sqlite = _drop_times(_run_contract(sqlite_repo))

    assert sqlite == postgres


def test_repository_reports_the_same_public_method_surface(postgres_repo, sqlite_repo):
    def surface(repository):
        return sorted(
            name
            for name in dir(repository)
            if not name.startswith("_") and callable(getattr(repository, name))
        )

    assert surface(sqlite_repo) == surface(postgres_repo)


# ── tenant isolation ───────────────────────────────────────────────


def test_settings_of_one_user_never_reach_another(sqlite_repo):
    assert sqlite_repo.save_settings("user-a", {"theme": "dark"}) is True
    assert sqlite_repo.save_settings("user-b", {"theme": "dark"}) is True

    sqlite_repo.save_settings("user-b", {"theme": "midnight", "show_grid": False})
    sqlite_repo.set_last_active_workspace("user-b", "beta")

    assert sqlite_repo.get_settings("user-a")["theme"] == "dark"
    assert sqlite_repo.get_settings("user-a")["show_grid"] is True
    assert sqlite_repo.get_last_active_workspace("user-a") == "session_mt5"
    assert sqlite_repo.get_settings("user-b")["theme"] == "midnight"
    assert sqlite_repo.get_settings("user-b")["show_grid"] is False


def test_workspaces_of_one_user_never_reach_another(sqlite_repo):
    sqlite_repo.save_workspace("user-a", "alpha", {"layout": "grid", "symbol": "MNQ"})
    sqlite_repo.save_workspace("user-b", "alpha", {"layout": "single", "symbol": "ES"})

    assert sqlite_repo.get_workspace("user-a", "alpha")["layout"] == "grid"
    assert sqlite_repo.get_workspace("user-b", "alpha")["layout"] == "single"
    assert sqlite_repo.get_workspace("user-b", "alpha")["symbol"] == "ES"
    assert set(sqlite_repo.get_all_workspaces("user-a")) == {"alpha"}

    assert sqlite_repo.delete_workspace("user-a", "alpha") is True
    assert sqlite_repo.get_workspace("user-a", "alpha") is None
    assert sqlite_repo.get_workspace("user-b", "alpha")["layout"] == "single"


def test_chat_history_of_one_user_never_reaches_another(sqlite_repo):
    sqlite_repo.save_ai_chat_message("user-a", "user", "from-a")
    sqlite_repo.save_ai_chat_message("user-b", "user", "from-b")
    sqlite_repo.save_ai_chat_message("user-b", "assistant", "b-answer")

    assert [row["content"] for row in sqlite_repo.get_ai_chat_history("user-a")] == [
        "from-a"
    ]
    assert [row["content"] for row in sqlite_repo.get_ai_chat_history("user-b")] == [
        "from-b",
        "b-answer",
    ]

    sqlite_repo.clear_ai_chat_history("user-a")
    assert sqlite_repo.get_ai_chat_history("user-a") == []
    assert len(sqlite_repo.get_ai_chat_history("user-b")) == 2


def test_algolab_state_of_one_user_never_reaches_another(sqlite_repo):
    sqlite_repo.save_algolab_state(
        "user-a", {"active_file_path": "a.py", "file_contents": {"a.py": "A"}}
    )
    sqlite_repo.save_algolab_state("user-b", {"open_files": [], "file_contents": {}})

    assert sqlite_repo.get_algolab_state("user-a")["active_file_path"] == "a.py"
    assert sqlite_repo.get_algolab_state("user-b")["active_file_path"] is None


def test_accounts_of_one_user_never_reach_another(sqlite_repo):
    sqlite_repo.upsert_account(
        user_id="user-a", platform="mt5", account_id="shared-id",
        metadata={"name": "A"}, credential_blob="blob-a",
    )
    sqlite_repo.upsert_account(
        user_id="user-b", platform="mt5", account_id="shared-id",
        metadata={"name": "B"}, credential_blob="blob-b",
    )

    assert sqlite_repo.get_account(
        user_id="user-a", platform="mt5", account_id="shared-id"
    )["credential_blob"] == "blob-a"
    assert sqlite_repo.get_account(
        user_id="user-b", platform="mt5", account_id="shared-id"
    )["metadata"] == {"name": "B"}

    assert sqlite_repo.delete_account(
        user_id="user-a", platform="mt5", account_id="shared-id"
    ) is True
    assert sqlite_repo.get_account(
        user_id="user-b", platform="mt5", account_id="shared-id"
    )["credential_blob"] == "blob-b"


def test_a_hostile_user_id_stays_a_bound_parameter(sqlite_repo):
    hostile = "user'); DROP TABLE workspaces;--"

    assert sqlite_repo.save_settings(hostile, {"theme": "light"}) is True
    assert sqlite_repo.save_workspace(hostile, "alpha", {"layout": "grid"}) is True

    assert sqlite_repo.get_settings(hostile)["theme"] == "light"
    assert sqlite_repo.get_workspace(hostile, "alpha")["layout"] == "grid"
    assert sqlite_repo.get_settings("user-a")["theme"] == "dark"
    assert sqlite_repo.get_all_workspaces("user-a") == {}


# ── backend selection ──────────────────────────────────────────────


def test_the_sqlite_switch_selects_the_sqlite_repository(monkeypatch, tmp_path):
    target = tmp_path / "local.db"
    monkeypatch.setenv(STORAGE_ENV, "sqlite")
    monkeypatch.setenv(SQLITE_PATH_ENV, str(target))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    repository = user_repository.get_repository()

    assert isinstance(repository, SqliteUserRepository)
    assert repository.path == str(target)
    repository.ensure_schema()
    assert repository.get_settings("user-a")["theme"] == "dark"


def test_the_facade_answers_from_sqlite_when_the_switch_is_on(monkeypatch, tmp_path):
    monkeypatch.setenv(STORAGE_ENV, "sqlite")
    monkeypatch.setenv(SQLITE_PATH_ENV, str(tmp_path / "local.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    user_repository.get_repository().ensure_schema()

    assert database.save_settings({"theme": "light"}, user_id="user-a") is True
    assert database.get_settings(user_id="user-a")["theme"] == "light"
    assert database.get_settings(user_id="user-b")["theme"] == "dark"


def test_the_default_sqlite_path_is_the_config_file(monkeypatch):
    monkeypatch.setenv(STORAGE_ENV, "sqlite")
    monkeypatch.delenv(SQLITE_PATH_ENV, raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    repository = user_repository.get_repository()

    assert isinstance(repository, SqliteUserRepository)
    assert repository.path == str(DEFAULT_SQLITE_PATH)


def test_an_unset_switch_keeps_the_postgres_repository(monkeypatch):
    monkeypatch.delenv(STORAGE_ENV, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://synthetic.invalid/app")

    repository = user_repository.get_repository()

    assert isinstance(repository, PostgresUserRepository)
    assert repository.url == "postgresql://synthetic.invalid/app"


def test_an_unset_switch_still_requires_database_url(monkeypatch, tmp_path):
    monkeypatch.delenv(STORAGE_ENV, raising=False)
    monkeypatch.setenv(SQLITE_PATH_ENV, str(tmp_path / "present.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(DatabaseNotConfigured) as excinfo:
        user_repository.get_repository()

    assert "DATABASE_URL" in str(excinfo.value)


def test_postgres_wins_even_when_a_sqlite_file_exists(monkeypatch, tmp_path):
    target = tmp_path / "present.db"
    local = SqliteUserRepository(str(target))
    local.ensure_schema()
    local.save_settings("user-a", {"theme": "from-sqlite"})
    assert target.exists()

    monkeypatch.setenv(STORAGE_ENV, "postgres")
    monkeypatch.setenv(SQLITE_PATH_ENV, str(target))
    monkeypatch.setenv("DATABASE_URL", "postgresql://synthetic.invalid/app")

    repository = user_repository.get_repository()

    assert isinstance(repository, PostgresUserRepository)
    assert repository.url == "postgresql://synthetic.invalid/app"


def test_install_and_reset_repository_still_override_the_switch(monkeypatch, tmp_path):
    installed = SqliteUserRepository(str(tmp_path / "installed.db"))
    monkeypatch.setenv("DATABASE_URL", "postgresql://synthetic.invalid/app")

    user_repository.set_repository(installed)
    assert user_repository.get_repository() is installed

    user_repository.reset_repository()
    assert user_repository.get_repository() is not installed


# ── cloud to local copy ────────────────────────────────────────────


def _seed_cloud(repository):
    """Rows a cloud deployment already holds, including an encrypted blob."""
    repository.save_settings("user-a", {"theme": "light", "last_active_workspace": "alpha"})
    repository.save_workspace(
        "user-a", "alpha", {"layout": "grid", "symbol": "ES", "charts": [{"id": 7}]}
    )
    repository.save_ai_chat_message("user-a", "user", "hello")
    repository.save_ai_chat_message("user-a", "assistant", "hi", skill="algolab")
    repository.save_algolab_state(
        "user-a", {"active_file_path": "a.py", "chat_width": 420, "is_chat_open": True}
    )
    repository.upsert_account(
        user_id="user-a", platform="mt5", account_id="cloud-1",
        metadata={"name": "Cloud account"}, credential_blob="ciphertext-for-user-a",
    )
    repository.save_settings("user-b", {"theme": "dark"})


def _observed_rows(repository):
    """Every copied row, read back through the repository's public interface."""
    return {
        "user_settings": [
            _drop_times(repository.get_settings(user)) for user in ("user-a", "user-b")
        ],
        "workspaces": repository.get_all_workspaces("user-a"),
        "ai_chat_history": _drop_times(repository.get_ai_chat_history("user-a")),
        "algolab_state": _drop_times(repository.get_algolab_state("user-a")),
        "broker_accounts": _drop_times(repository.list_accounts(user_id="user-a")),
    }


def test_the_copy_moves_every_table_verbatim(postgres_repo, sqlite_repo):
    _seed_cloud(postgres_repo)

    counts = migration.migrate_cloud_to_sqlite(postgres_repo, sqlite_repo)

    assert counts["user_settings"] == {"inserted": 2, "updated": 0, "skipped": 0}
    assert counts["workspaces"] == {"inserted": 1, "updated": 0, "skipped": 0}
    assert counts["ai_chat_history"] == {"inserted": 2, "updated": 0, "skipped": 0}
    assert counts["algolab_state"] == {"inserted": 1, "updated": 0, "skipped": 0}
    assert counts["broker_accounts"] == {"inserted": 1, "updated": 0, "skipped": 0}

    assert _observed_rows(sqlite_repo) == _observed_rows(postgres_repo)


def test_the_copy_keeps_the_encrypted_blob_unchanged(postgres_repo, sqlite_repo):
    _seed_cloud(postgres_repo)

    migration.migrate_cloud_to_sqlite(postgres_repo, sqlite_repo)

    copied = sqlite_repo.get_account(
        user_id="user-a", platform="mt5", account_id="cloud-1"
    )
    assert copied["credential_blob"] == "ciphertext-for-user-a"
    assert copied["metadata"] == {"name": "Cloud account"}


def test_running_the_copy_twice_leaves_the_same_rows(postgres_repo, sqlite_repo):
    _seed_cloud(postgres_repo)
    migration.migrate_cloud_to_sqlite(postgres_repo, sqlite_repo)
    before = _observed_rows(sqlite_repo)

    second = migration.migrate_cloud_to_sqlite(postgres_repo, sqlite_repo)

    assert second["user_settings"] == {"inserted": 0, "updated": 0, "skipped": 2}
    assert second["workspaces"] == {"inserted": 0, "updated": 0, "skipped": 1}
    assert second["ai_chat_history"] == {"inserted": 0, "updated": 0, "skipped": 2}
    assert second["algolab_state"] == {"inserted": 0, "updated": 0, "skipped": 1}
    assert second["broker_accounts"] == {"inserted": 0, "updated": 0, "skipped": 1}
    assert _observed_rows(sqlite_repo) == before


def test_the_copy_updates_a_row_the_cloud_changed(postgres_repo, sqlite_repo):
    _seed_cloud(postgres_repo)
    migration.migrate_cloud_to_sqlite(postgres_repo, sqlite_repo)

    postgres_repo.save_settings("user-a", {"theme": "solarized"})
    counts = migration.migrate_cloud_to_sqlite(postgres_repo, sqlite_repo)

    assert counts["user_settings"] == {"inserted": 0, "updated": 1, "skipped": 1}
    assert sqlite_repo.get_settings("user-a")["theme"] == "solarized"


# ── legacy compatibility, same marker discipline as Postgres ──────


def _legacy_file(path):
    """A pre-migration SQLite file holding desktop rows under ``default_user``."""
    import sqlite3

    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE user_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default_user' UNIQUE,
            platform TEXT DEFAULT 'mt5',
            theme TEXT DEFAULT 'dark'
        );
        CREATE TABLE workspaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default_user',
            session_name TEXT NOT NULL,
            layout TEXT DEFAULT 'single',
            UNIQUE(user_id, session_name)
        );
        """
    )
    connection.execute(
        "INSERT INTO user_settings (user_id, theme) VALUES ('default_user', 'legacy')"
    )
    connection.execute(
        "INSERT INTO workspaces (user_id, session_name) VALUES ('default_user', 'legacy_ws')"
    )
    connection.commit()
    connection.close()
    return str(path)


def test_the_legacy_sqlite_import_is_marker_guarded_and_never_itself(tmp_path):
    source = _legacy_file(tmp_path / "legacy.db")
    local = SqliteUserRepository(str(tmp_path / "local.db"))
    local.ensure_schema()

    first = local.import_legacy_sqlite(source)
    assert first["status"] == "applied"
    assert first["imported"]["user_settings"] == 1
    assert first["imported"]["workspaces"] == 1
    assert local.get_settings("default_user")["theme"] == "legacy"
    assert local.get_workspace("default_user", "legacy_ws") is not None

    assert local.legacy_import_applied() is True
    assert local.import_legacy_sqlite(source)["status"] == "skipped_already_applied"

    # A local run serves the file it would import, so startup imports nothing.
    assert local.import_legacy_sqlite(local.path)["status"] == "skipped_same_file"

    removed = local.delete_user_rows("default_user")
    assert removed["user_settings"] == 1
    assert removed["workspaces"] == 1
    local.clear_legacy_import_marker()
    assert local.legacy_import_applied() is False


def test_the_legacy_json_account_import_is_marker_guarded(tmp_path):
    import json

    accounts = tmp_path / "mt5_accounts.json"
    accounts.write_text(
        json.dumps(
            [{"id": "legacy-1", "name": "Legacy", "created_at": "2025-01-01T00:00:00"}]
        ),
        encoding="utf-8",
    )
    local = SqliteUserRepository(str(tmp_path / "local.db"))
    local.ensure_schema()

    first = local.import_legacy_accounts({"mt5": str(accounts)})
    assert first == {"status": "applied", "imported": {"mt5": 1}}
    stored = local.get_account(
        user_id="default_user", platform="mt5", account_id="legacy-1"
    )
    assert stored["metadata"]["name"] == "Legacy"
    assert stored["credential_blob"] == ""

    assert local.import_legacy_accounts({"mt5": str(accounts)}) == {
        "status": "skipped_already_applied",
        "imported": {},
    }
    assert len(local.list_accounts(user_id="default_user")) == 1


def test_the_report_prints_counts_and_never_a_credential(
    postgres_repo, sqlite_repo, monkeypatch, tmp_path, capsys
):
    _seed_cloud(postgres_repo)
    monkeypatch.setenv("DATABASE_URL", "postgresql://synthetic.invalid/app")
    monkeypatch.setattr(migration, "PostgresUserRepository", lambda url: postgres_repo)
    target = tmp_path / "migrated.db"

    exit_code = migration.main(["--sqlite-path", str(target)])
    printed = capsys.readouterr().out

    assert exit_code == 0
    assert "user_settings" in printed
    assert "inserted=2" in printed
    assert "broker_accounts" in printed
    assert "ciphertext-for-user-a" not in printed
    assert target.exists()
