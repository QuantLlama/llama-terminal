"""The off-host backup must encrypt, upload and prune without leaking secrets."""
import importlib.util
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("backup_to_r2", ROOT / "scripts/backup_to_r2.py")
backup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup)


class FakeClient:
    def __init__(self, existing=()):
        self.uploaded = []
        self.deleted = []
        self.existing = list(existing)

    def upload_file(self, filename, bucket, key):
        self.uploaded.append((filename, bucket, key))

    def list_objects_v2(self, Bucket, Prefix):
        return {"Contents": [{"Key": key} for key in self.existing]}

    def delete_object(self, Bucket, Key):
        self.deleted.append(Key)


def _env(monkeypatch):
    monkeypatch.setenv("R2_ENDPOINT", "https://example.invalid")
    monkeypatch.setenv("R2_BUCKET", "bucket")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("BACKUP_PASSPHRASE", "passphrase")


def test_missing_configuration_is_reported_not_guessed(monkeypatch):
    for name in backup.REQUIRED:
        monkeypatch.delenv(name, raising=False)
    assert set(backup.missing_configuration()) == set(backup.REQUIRED)
    assert backup.main() == 2


def test_archive_name_is_stamped_and_encrypted_suffix():
    name = backup.archive_name(datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
    assert name == "quantum-llama-20260102T030405Z.tar.gz.enc"


def test_build_archive_encrypts_and_removes_the_plain_file(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_PASSPHRASE", "passphrase")
    source = tmp_path / "config"
    source.mkdir()
    (source / "quantum_llama.db").write_bytes(b"sqlite-bytes")
    out = tmp_path / "a.tar.gz.enc"

    size = backup.build_archive([str(source)], out)

    assert out.exists() and size == out.stat().st_size
    blob = out.read_bytes()
    assert b"sqlite-bytes" not in blob, "the archive must not leak the database in clear text"
    assert not (tmp_path / "a.tar.gz").exists()


def test_upload_and_prune_keep_only_the_newest(monkeypatch):
    client = FakeClient(
        existing=[
            "backups/quantum-llama-20260101T000000Z.tar.gz.enc",
            "backups/quantum-llama-20260102T000000Z.tar.gz.enc",
            "backups/quantum-llama-20260103T000000Z.tar.gz.enc",
            "backups/notes.txt",
        ]
    )
    removed = backup.prune(client, "bucket", "backups/", keep=2)
    assert removed == ["backups/quantum-llama-20260101T000000Z.tar.gz.enc"]
    assert client.deleted == removed
    assert not any(key.endswith("notes.txt") for key in client.deleted)


def test_credentials_are_never_printed(monkeypatch, capsys, tmp_path):
    _env(monkeypatch)
    monkeypatch.setenv("BACKUP_SOURCES", str(tmp_path))
    monkeypatch.setattr(backup, "_client", lambda: FakeClient())
    assert backup.main() == 0
    out = capsys.readouterr()
    combined = out.out + out.err
    for secret in ("secret", "passphrase", "key"):
        assert secret not in combined.replace("uploaded", ""), f"leaked {secret}"
    assert "backup: uploaded" in out.out
