"""Postgres-backed broker accounts, their per-user keys and the one-time import.

Every test runs against the fake DB-API driver from ``test_database_postgres``:
no socket, no real database, no real credential. Broker accounts moved out of
``src/config/*_accounts.json`` into PostgreSQL, one row per tenant, so the
assertions here are about a mandatory ``user_id``, statement parameterization,
per-user encryption keys and a marker-guarded JSON import.
"""
import json
from pathlib import Path

import pytest

from src.services import database, user_repository
from src.services.credential_manager import UserCredentialVault
from src.services.user_repository import (
    LEGACY_ACCOUNT_IMPORT_MARKER,
    PostgresUserRepository,
)
from test_database_postgres import FakePostgres, open_fake_connection

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def store(monkeypatch):
    fake = FakePostgres()
    monkeypatch.setattr(user_repository, "_open_connection", open_fake_connection(fake))
    return fake


@pytest.fixture
def repo(store):
    repository = PostgresUserRepository("postgresql://synthetic.invalid/per_user")
    repository.ensure_schema()
    database.set_repository(repository)
    try:
        yield repository
    finally:
        database.reset_repository()
        user_repository.reset_repository()


# ── schema ─────────────────────────────────────────────────────────


def test_schema_declares_the_broker_accounts_table(store, repo):
    ddl = "\n".join(sql for sql, _ in store.statements)

    assert "CREATE TABLE IF NOT EXISTS broker_accounts" in ddl
    assert "user_id TEXT NOT NULL" in ddl
    assert "platform TEXT NOT NULL" in ddl
    assert "account_id TEXT NOT NULL" in ddl
    assert "metadata JSONB NOT NULL DEFAULT '{}'" in ddl
    assert "credential_blob TEXT" in ddl
    assert "UNIQUE (user_id, platform, account_id)" in ddl
    assert "CREATE INDEX IF NOT EXISTS idx_broker_accounts_user_id ON broker_accounts (user_id)" in ddl
    # The shared tenant of the JSON era must not come back.
    assert "default_user" not in ddl


def test_accounts_schema_creation_is_idempotent(store, repo):
    first_run = len(store.statements)
    repo.ensure_schema()
    statements = store.statements[first_run:]
    assert statements
    assert all(sql.strip().upper().startswith(("CREATE", "ALTER")) for sql, _ in statements)
    assert all(params is None for _, params in statements)
    assert len(statements) == first_run


# ── structural guard: no implicit tenant ───────────────────────────


@pytest.mark.parametrize(
    "call",
    [
        lambda repository: repository.list_accounts(),
        lambda repository: repository.get_account(platform="mt5", account_id="a1"),
        lambda repository: repository.upsert_account(
            platform="mt5", account_id="a1", metadata={}
        ),
        lambda repository: repository.delete_account(platform="mt5", account_id="a1"),
        lambda repository: database.list_accounts(),
        lambda repository: database.get_account(platform="mt5", account_id="a1"),
        lambda repository: database.upsert_account(
            platform="mt5", account_id="a1", metadata={}
        ),
        lambda repository: database.delete_account(platform="mt5", account_id="a1"),
    ],
)
def test_account_crud_without_user_id_is_a_type_error(repo, store, call):
    with pytest.raises(TypeError):
        call(repo)
    assert store.rows("broker_accounts") == []


def test_user_id_is_keyword_only_so_positional_calls_cannot_guess_a_tenant(repo):
    with pytest.raises(TypeError):
        repo.list_accounts("user-a")
    with pytest.raises(TypeError):
        database.list_accounts("user-a")


# ── per-user reads and writes ──────────────────────────────────────


def test_accounts_are_scoped_to_their_owner(repo):
    repo.upsert_account(
        user_id="user-a", platform="mt5", account_id="a1",
        metadata={"name": "A-account"}, credential_blob="blob-a",
    )
    repo.upsert_account(
        user_id="user-b", platform="mt5", account_id="b1",
        metadata={"name": "B-account"}, credential_blob="blob-b",
    )

    listed_a = repo.list_accounts(user_id="user-a")
    assert [row["account_id"] for row in listed_a] == ["a1"]
    assert listed_a[0]["metadata"] == {"name": "A-account"}
    assert repo.get_account(user_id="user-a", platform="mt5", account_id="b1") is None
    assert repo.delete_account(user_id="user-a", platform="mt5", account_id="b1") is False
    assert repo.get_account(user_id="user-b", platform="mt5", account_id="b1")["metadata"] == {
        "name": "B-account"
    }


def test_the_same_account_id_belongs_to_two_tenants_without_collision(repo, store):
    repo.upsert_account(
        user_id="user-a", platform="mt5", account_id="shared-id",
        metadata={"name": "A"}, credential_blob="blob-a",
    )
    repo.upsert_account(
        user_id="user-b", platform="mt5", account_id="shared-id",
        metadata={"name": "B"}, credential_blob="blob-b",
    )

    assert repo.get_account(user_id="user-a", platform="mt5", account_id="shared-id")[
        "metadata"
    ] == {"name": "A"}
    assert repo.get_account(user_id="user-b", platform="mt5", account_id="shared-id")[
        "metadata"
    ] == {"name": "B"}
    assert len(store.rows("broker_accounts")) == 2


def test_upsert_updates_one_row_and_never_touches_a_neighbour(repo, store):
    repo.upsert_account(
        user_id="user-b", platform="mt5", account_id="b1",
        metadata={"name": "B-original"}, credential_blob="blob-b",
    )
    repo.upsert_account(
        user_id="user-a", platform="mt5", account_id="a1",
        metadata={"name": "A-first"}, credential_blob="blob-a",
    )
    repo.upsert_account(
        user_id="user-a", platform="mt5", account_id="a1",
        metadata={"name": "A-second", "status": "active"}, credential_blob="blob-a2",
    )

    rows = [
        (row["user_id"], row["account_id"], row["credential_blob"])
        for row in store.rows("broker_accounts")
    ]
    assert sorted(rows) == [("user-a", "a1", "blob-a2"), ("user-b", "b1", "blob-b")]
    assert repo.get_account(user_id="user-a", platform="mt5", account_id="a1")["metadata"] == {
        "name": "A-second",
        "status": "active",
    }


def test_a_platform_scoped_delete_leaves_the_other_platform_alone(repo):
    repo.upsert_account(
        user_id="user-a", platform="mt5", account_id="same", metadata={"name": "mt5"}
    )
    repo.upsert_account(
        user_id="user-a", platform="nt8", account_id="same", metadata={"name": "nt8"}
    )

    assert repo.delete_account(user_id="user-a", platform="nt8", account_id="same") is True
    assert repo.get_account(user_id="user-a", platform="nt8", account_id="same") is None
    assert repo.get_account(user_id="user-a", platform="mt5", account_id="same") is not None


def test_every_account_statement_binds_the_tenant_instead_of_interpolating(repo, store):
    repo.upsert_account(
        user_id="user-a", platform="mt5", account_id="a1", metadata={"name": "A"}
    )
    repo.list_accounts(user_id="user-a")
    repo.get_account(user_id="user-a", platform="mt5", account_id="a1")
    repo.delete_account(user_id="user-a", platform="mt5", account_id="a1")

    account_statements = [
        (sql, params)
        for sql, params in store.statements
        if "broker_accounts" in sql and not sql.strip().upper().startswith(("CREATE", "ALTER"))
    ]
    assert len(account_statements) >= 4
    for sql, params in account_statements:
        assert "user-a" not in sql, sql
        assert isinstance(params, dict)
        assert params.get("user_id") == "user-a"
        assert "%(user_id)s" in sql
        assert user_repository.DEFAULT_USER_ID not in str(params)


# ── per-user key material ──────────────────────────────────────────


def test_user_key_material_only_decrypts_that_users_blob():
    vault = UserCredentialVault(master_key=b"synthetic-master-secret")
    blob = vault.manager_for("user-a").encrypt(json.dumps({"password": "synthetic"}))

    assert json.loads(vault.manager_for("user-a").decrypt(blob)) == {"password": "synthetic"}
    assert vault.manager_for("user-b").decrypt(blob) == "DECRYPTION_FAILED"
    assert vault.key_for("user-a") != vault.key_for("user-b")


def test_another_installation_master_key_cannot_decrypt_the_blob():
    blob = UserCredentialVault(master_key=b"installation-one").manager_for("user-a").encrypt(
        json.dumps({"password": "synthetic"})
    )
    other = UserCredentialVault(master_key=b"installation-two")
    assert other.manager_for("user-a").decrypt(blob) == "DECRYPTION_FAILED"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_key_derivation_refuses_an_empty_identity(value):
    vault = UserCredentialVault(master_key=b"synthetic-master-secret")
    with pytest.raises(TypeError):
        vault.key_for(value)


def test_key_derivation_requires_an_identity_argument():
    vault = UserCredentialVault(master_key=b"synthetic-master-secret")
    with pytest.raises(TypeError):
        vault.key_for()


def test_stored_credentials_are_ciphertext_for_the_owner_only(repo):
    vault = UserCredentialVault(master_key=b"synthetic-master-secret")
    repo.upsert_account(
        user_id="user-a",
        platform="crypto",
        account_id="c1",
        metadata={"name": "A"},
        credential_blob=vault.manager_for("user-a").encrypt(
            json.dumps({"api_secret": "synthetic-secret"})
        ),
    )

    stored = repo.list_accounts(user_id="user-a")[0]["credential_blob"]
    assert "synthetic-secret" not in stored
    assert json.loads(vault.manager_for("user-a").decrypt(stored)) == {
        "api_secret": "synthetic-secret"
    }
    assert vault.manager_for("user-b").decrypt(stored) == "DECRYPTION_FAILED"


# ── one-time JSON import ───────────────────────────────────────────


def _legacy_file(tmp_path: Path, name: str, accounts: dict) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(accounts))
    return str(path)


MT5_ACCOUNTS = {
    "abc12345": {
        "id": "abc12345",
        "name": "AMP demo",
        "broker": "AMP",
        "server": "AMPGlobalUSA-Demo",
        "login": "5001",
        "password": "legacy-ciphertext",
        "account_type": "demo",
        "created_at": "2024-01-01T00:00:00",
        "status": "inactive",
        "is_master": False,
        "instance_path": None,
    }
}

CRYPTO_ACCOUNTS = {
    "def67890": {
        "id": "def67890",
        "name": "bybit main",
        "broker": "bybit",
        "api_key": "public-key",
        "api_secret": "legacy-ciphertext",
        "passphrase": "",
        "account_type": "live",
        "created_at": "2024-01-02T00:00:00",
        "status": "inactive",
        "is_master": False,
        "platform": "crypto",
    }
}


def test_legacy_json_imports_once_into_the_configured_account(repo, store, tmp_path, monkeypatch):
    monkeypatch.setenv(user_repository.LEGACY_IMPORT_TARGET_ENV, "owner-1")
    files = {
        "mt5": _legacy_file(tmp_path, "mt5_accounts.json", MT5_ACCOUNTS),
        "crypto": _legacy_file(tmp_path, "crypto_accounts.json", CRYPTO_ACCOUNTS),
    }

    result = repo.import_legacy_accounts(files)
    assert result["status"] == "applied"
    assert result["imported"] == {"mt5": 1, "crypto": 1}

    rows = store.rows("broker_accounts")
    assert {row["user_id"] for row in rows} == {"owner-1"}
    assert {row["platform"] for row in rows} == {"mt5", "crypto"}
    assert {row["account_id"] for row in rows} == {"abc12345", "def67890"}
    # Encrypted secrets are never copied into metadata.
    for row in rows:
        assert "legacy-ciphertext" not in json.dumps(row["metadata"])
        assert "password" not in row["metadata"]
    assert [row["name"] for row in store.rows("migration_state")] == [
        LEGACY_ACCOUNT_IMPORT_MARKER
    ]

    before = store.snapshot()
    second = repo.import_legacy_accounts(files)
    assert second["status"] == "skipped_already_applied"
    assert second["imported"] == {}
    assert store.snapshot() == before


def test_legacy_json_import_never_overwrites_postgres_rows(repo, store, tmp_path, monkeypatch):
    monkeypatch.setenv(user_repository.LEGACY_IMPORT_TARGET_ENV, "owner-1")
    repo.upsert_account(
        user_id="owner-1",
        platform="mt5",
        account_id="abc12345",
        metadata={"name": "postgres-wins"},
        credential_blob="postgres-blob",
    )

    result = repo.import_legacy_accounts(
        {"mt5": _legacy_file(tmp_path, "mt5_accounts.json", MT5_ACCOUNTS)}
    )
    assert result["status"] == "applied"
    assert result["imported"] == {"mt5": 0}
    assert repo.get_account(user_id="owner-1", platform="mt5", account_id="abc12345")[
        "metadata"
    ] == {"name": "postgres-wins"}


def test_legacy_json_import_tolerates_missing_and_unreadable_files(repo, store, tmp_path):
    unreadable = tmp_path / "broken_accounts.json"
    unreadable.write_text("{not json")
    files = {"mt5": str(tmp_path / "absent.json"), "crypto": str(unreadable)}

    result = repo.import_legacy_accounts(files)
    assert result["status"] == "skipped_missing_file"
    assert result["imported"] == {"mt5": 0, "crypto": 0}
    assert store.rows("broker_accounts") == []
    assert store.rows("migration_state") == []

    # The marker was not consumed, so a later run with a readable file still imports.
    later = repo.import_legacy_accounts(
        {"mt5": _legacy_file(tmp_path, "mt5_accounts.json", MT5_ACCOUNTS)}
    )
    assert later["status"] == "applied"
    assert later["imported"] == {"mt5": 1}


def test_legacy_json_import_skips_entries_without_an_account_id(repo, store, tmp_path):
    files = {"mt5": _legacy_file(tmp_path, "mt5_accounts.json", {"no-id": {"name": "x"}})}
    result = repo.import_legacy_accounts(files)
    assert result["imported"] == {"mt5": 0}
    assert store.rows("broker_accounts") == []


def test_legacy_json_import_accepts_a_list_shaped_file(repo, store, tmp_path):
    path = tmp_path / "nt8_accounts.json"
    path.write_text(json.dumps([{"id": "n1", "name": "bridge", "exchange_dir": "/tmp/x"}]))
    result = repo.import_legacy_accounts({"nt8": str(path)})
    assert result["imported"] == {"nt8": 1}
    assert repo.get_account(user_id=user_repository.DEFAULT_USER_ID, platform="nt8", account_id="n1")


def test_legacy_json_import_reads_the_container_paths_not_the_worktree(repo, store, tmp_path, monkeypatch):
    """The importer resolves paths through the shared data-path helper."""
    data_root = tmp_path / "app"
    (data_root / "src" / "config").mkdir(parents=True)
    (data_root / "src" / "config" / "mt5_accounts.json").write_text(json.dumps(MT5_ACCOUNTS))
    monkeypatch.setattr(database, "get_data_path", lambda *parts: str(data_root.joinpath(*parts)))

    files = database.legacy_account_files()
    assert files["mt5"].endswith("mt5_accounts.json")
    assert files["mt5"].startswith(str(data_root))
    assert database.import_legacy_accounts()["imported"] == {"mt5": 1, "crypto": 0, "nt8": 0}
