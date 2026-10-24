"""The one-shot desktop import transport must be inert unless explicitly armed."""
import importlib
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.platform.api import migration_api

SQLITE_HEADER = b"SQLite format 3\x00" + b"payload"


@pytest.fixture
def client(tmp_path, monkeypatch):
    module = importlib.reload(migration_api)
    store = {"applied": False, "imported": None, "path": tmp_path / "quantum_llama.db"}

    monkeypatch.setattr(module.database, "get_db_path", lambda: str(store["path"]))
    monkeypatch.setattr(module.database, "legacy_import_already_applied", lambda: store["applied"])
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
