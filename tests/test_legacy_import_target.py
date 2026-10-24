"""Importing pre-migration SQLite data into a chosen account.

An owner migrating from the desktop app must be able to land their existing
workspaces and settings under their own web identity instead of a shared
``default_user`` placeholder.
"""
import sqlite3
from pathlib import Path

import pytest

from src.services import user_repository


def _legacy_db(path: Path) -> Path:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE user_settings (user_id TEXT, platform TEXT, theme TEXT);
        CREATE TABLE workspaces (user_id TEXT, session_name TEXT, data TEXT);
        INSERT INTO user_settings VALUES ('default_user', 'mt5', 'dark');
        INSERT INTO workspaces VALUES ('default_user', 'session_mt5', '{"a":1}');
        """
    )
    connection.commit()
    connection.close()
    return path


def test_import_targets_the_configured_account(tmp_path, monkeypatch):
    legacy = _legacy_db(tmp_path / "quantum_llama.db")
    target = "0bc8f372-83ee-4ba7-bc33-97a518e5b029"
    monkeypatch.setenv(user_repository.LEGACY_IMPORT_TARGET_ENV, target)
    assert user_repository.legacy_import_user_id() == target
    rows = user_repository._read_legacy_rows(str(legacy))
    assert rows is not None
    for table_rows in rows.values():
        for row in table_rows:
            assert row["user_id"] == target, "rows must carry the configured identity"


@pytest.mark.parametrize("value", ["two words", "a/b", "x" * 200])
def test_invalid_import_identity_is_refused(monkeypatch, value):
    monkeypatch.setenv(user_repository.LEGACY_IMPORT_TARGET_ENV, value)
    with pytest.raises(ValueError):
        user_repository.legacy_import_user_id()


@pytest.mark.parametrize("value", [None, "", "   "])
def test_absent_override_keeps_the_historical_default(monkeypatch, value):
    if value is None:
        monkeypatch.delenv(user_repository.LEGACY_IMPORT_TARGET_ENV, raising=False)
    else:
        monkeypatch.setenv(user_repository.LEGACY_IMPORT_TARGET_ENV, value)
    assert user_repository.legacy_import_user_id() == user_repository.DEFAULT_USER_ID
