"""Configuration tests for credential encryption keys.

Cloud deployments run the app as a non-root user with a read-only project
root, so the key location must be overridable through
QUANTUM_LLAMA_KEY_DIR while the desktop default stays unchanged.
"""

import os

import pytest

from src.services.security import CredentialManager


def test_key_dir_env_controls_key_location(monkeypatch, tmp_path):
    key_dir = tmp_path / "keys"
    monkeypatch.setenv("QUANTUM_LLAMA_KEY_DIR", str(key_dir))

    manager = CredentialManager(key_file=".mt5_key")

    assert manager.key_file == str(key_dir / ".mt5_key")
    assert os.path.exists(manager.key_file)


def test_keys_persist_and_round_trip_inside_key_dir(monkeypatch, tmp_path):
    key_dir = tmp_path / "keys"
    monkeypatch.setenv("QUANTUM_LLAMA_KEY_DIR", str(key_dir))

    first = CredentialManager(key_file=".crypto_key")
    token = first.encrypt("secret-value")

    second = CredentialManager(key_file=".crypto_key")

    assert second.key == first.key, "the key must be reused across restarts"
    assert second.decrypt(token) == "secret-value"


def test_default_key_location_is_unchanged_without_env(monkeypatch):
    monkeypatch.delenv("QUANTUM_LLAMA_KEY_DIR", raising=False)

    manager = CredentialManager(key_file=".mt5_key")

    assert manager.key_file.endswith(os.path.join("", ".mt5_key"))
    assert os.path.dirname(manager.key_file) != ""
