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


class FakeRun:
    """Records subprocess invocations so the dump command can be asserted."""

    def __init__(self, writes=b"-- sql dump --"):
        self.calls = []
        self.writes = writes

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout=self.writes, stderr=b"")


def test_database_dump_is_encrypted_and_uploaded(monkeypatch, tmp_path):
    """A restore needs a real logical dump, produced inside the encrypted archive."""
    monkeypatch.setenv("BACKUP_PASSPHRASE", "passphrase")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pw@host:5432/db")
    runner = FakeRun()
    out = tmp_path / "db.tar.gz.enc"

    size = backup.build_database_archive(out, run=runner)

    assert out.exists() and size == out.stat().st_size
    argv, kwargs = runner.calls[0]
    assert argv[0] == "pg_dump", "the dump must come from pg_dump, not a hand-rolled serializer"
    assert "--no-owner" in argv and "--no-privileges" in argv
    assert kwargs.get("stdout") == subprocess.PIPE
    blob = out.read_bytes()
    assert b"-- sql dump --" not in blob, "the dump must never reach the bucket in clear text"


def test_database_dump_is_skipped_without_a_database_url(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKUP_PASSPHRASE", "passphrase")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    runner = FakeRun()
    result = backup.build_database_archive(tmp_path / "db.tar.gz.enc", run=runner)
    assert result == 0
    assert runner.calls == []


def test_a_failed_dump_is_reported_and_does_not_produce_an_archive(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKUP_PASSPHRASE", "passphrase")
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h:5432/d")

    def failing(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv, b"", b"pg_dump: error")

    out = tmp_path / "db.tar.gz.enc"
    with pytest.raises(subprocess.CalledProcessError):
        backup.build_database_archive(out, run=failing)
    assert not out.exists()


def test_database_archives_use_their_own_prefix_and_retention(monkeypatch, capsys):
    _env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h:5432/d")
    monkeypatch.setenv("BACKUP_DB_PREFIX", "backups/db")
    monkeypatch.setattr(backup, "_client", lambda: FakeClient())
    monkeypatch.setattr(backup, "build_archive", lambda sources, destination: 10)
    monkeypatch.setattr(backup, "build_database_archive", lambda destination, **kw: 20)
    assert backup.main() == 0
    out = capsys.readouterr().out
    assert "backups/db/" in out or "database" in out.lower()
