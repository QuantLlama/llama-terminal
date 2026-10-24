"""The one-shot desktop import transport must be inert unless explicitly armed."""
import importlib
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.platform.api import migration_api
from src.services import database as module_counts

SQLITE_HEADER = b"SQLite format 3\x00" + b"payload"


@pytest.fixture
def client(tmp_path, monkeypatch):
    module = importlib.reload(migration_api)
    store = {"applied": False, "imported": None, "path": tmp_path / "quantum_llama.db"}

    monkeypatch.setattr(module.database, "get_db_path", lambda: str(store["path"]))
    monkeypatch.setattr(module.database, "legacy_import_already_applied", lambda: store["applied"])
    monkeypatch.setattr(module.database, "legacy_import_user_id", lambda: "user-a")
    monkeypatch.setattr(
        module.database,
        "delete_user_rows",
        lambda user_id: store.update(replaced=user_id) or {"workspaces": 1},
    )
    monkeypatch.setattr(
        module.database,
        "clear_legacy_import_marker",
        lambda: store.update(applied=False, cleared=True),
    )
    monkeypatch.setattr(
        module.database,
        "import_legacy_sqlite",
        lambda path=None: store.update(imported=path) or {"status": "applied", "imported": {"workspaces": 2}},
    )
    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app), store, monkeypatch


def test_disabled_without_a_configured_token(client):
    http, _, monkeypatch = client
    monkeypatch.delenv(migration_api.TOKEN_ENV, raising=False)
    response = http.post("/api/ops/desktop-import", content=SQLITE_HEADER)
    assert response.status_code == 404


def test_wrong_token_is_rejected_and_writes_nothing(client):
    http, store, monkeypatch = client
    monkeypatch.setenv(migration_api.TOKEN_ENV, "expected-token")
    response = http.post(
        "/api/ops/desktop-import", content=SQLITE_HEADER, headers={"X-Import-Token": "nope"}
    )
    assert response.status_code == 401
    assert not store["path"].exists()


def test_missing_token_is_rejected(client):
    http, _, monkeypatch = client
    monkeypatch.setenv(migration_api.TOKEN_ENV, "expected-token")
    assert http.post("/api/ops/desktop-import", content=SQLITE_HEADER).status_code == 401


def test_a_real_sqlite_payload_is_stored_and_imported(client):
    http, store, monkeypatch = client
    monkeypatch.setenv(migration_api.TOKEN_ENV, "expected-token")
    response = http.post(
        "/api/ops/desktop-import", content=SQLITE_HEADER, headers={"X-Import-Token": "expected-token"}
    )
    assert response.status_code == 200
    assert response.json()["imported"] == {"workspaces": 2}
    assert store["path"].read_bytes() == SQLITE_HEADER
    assert oct(store["path"].stat().st_mode)[-3:] == "600"


def test_non_sqlite_payload_is_refused(client):
    http, store, monkeypatch = client
    monkeypatch.setenv(migration_api.TOKEN_ENV, "expected-token")
    response = http.post(
        "/api/ops/desktop-import", content=b"not a database", headers={"X-Import-Token": "expected-token"}
    )
    assert response.status_code == 400
    assert not store["path"].exists()


def test_refuses_once_the_import_marker_exists(client):
    http, store, monkeypatch = client
    monkeypatch.setenv(migration_api.TOKEN_ENV, "expected-token")
    store["applied"] = True
    response = http.post(
        "/api/ops/desktop-import", content=SQLITE_HEADER, headers={"X-Import-Token": "expected-token"}
    )
    assert response.status_code == 409
    assert not store["path"].exists()


def test_force_runs_once_more_without_deleting_rows(client):
    http, store, monkeypatch = client
    monkeypatch.setenv(migration_api.TOKEN_ENV, "expected-token")
    store["applied"] = True
    response = http.post(
        "/api/ops/desktop-import",
        content=SQLITE_HEADER,
        headers={"X-Import-Token": "expected-token", "X-Import-Force": "1"},
    )
    assert response.status_code == 200
    assert store.get("cleared") is True
    assert store["path"].read_bytes() == SQLITE_HEADER


def test_replace_clears_only_the_target_tenant_before_importing(client):
    http, store, monkeypatch = client
    monkeypatch.setenv(migration_api.TOKEN_ENV, "expected-token")
    store["applied"] = True
    response = http.post(
        "/api/ops/desktop-import",
        content=SQLITE_HEADER,
        headers={"X-Import-Token": "expected-token", "X-Import-Replace": "1"},
    )
    assert response.status_code == 200
    assert store["replaced"] == "user-a"
    assert response.json()["replaced"] == {"workspaces": 1}


def test_status_reports_counts_without_row_content(client):
    http, store, monkeypatch = client
    monkeypatch.setenv(migration_api.TOKEN_ENV, "expected-token")
    store["path"].write_bytes(SQLITE_HEADER)
    monkeypatch.setattr(
        module_counts, "legacy_table_counts", lambda _p: {"workspaces": 6, "user_settings": 1}
    )
    response = http.get(
        "/api/ops/desktop-import/status", headers={"X-Import-Token": "expected-token"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tables"] == {"workspaces": 6, "user_settings": 1}
    assert body["size"] == len(SQLITE_HEADER)
    assert body["target_user"] == "user-a"
