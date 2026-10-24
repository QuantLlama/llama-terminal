#!/usr/bin/env python3
"""Encrypted off-host backup of the platform data volumes.

Archives the persistent data directories, encrypts the archive and uploads it to
an S3-compatible bucket. Credentials and the passphrase come only from the
environment; nothing is written to disk in clear text and nothing is logged.

Environment:
    R2_ENDPOINT            S3 API endpoint
    R2_BUCKET              bucket name
    R2_ACCESS_KEY_ID       access key
    R2_SECRET_ACCESS_KEY   secret key
    BACKUP_PASSPHRASE      encryption passphrase (required)
    BACKUP_PREFIX          key prefix, default "backups"
    BACKUP_KEEP            archives to retain, default 14
    BACKUP_SOURCES         comma separated paths, default "/app/config,/app/logs"
"""
from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = ("R2_ENDPOINT", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "BACKUP_PASSPHRASE")


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def missing_configuration() -> list:
    return [name for name in REQUIRED if not _env(name)]


def archive_name(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"quantum-llama-{stamp}.tar.gz.enc"


def build_archive(sources, destination: Path) -> int:
    """Tar the existing sources, then encrypt the archive in place."""
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as handle:
        plain = Path(handle.name)
    try:
        with tarfile.open(plain, "w:gz") as tar:
            for source in sources:
                path = Path(source)
                if path.exists():
                    tar.add(str(path), arcname=path.name)
        subprocess.run(
            [
                "openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt",
                "-in", str(plain), "-out", str(destination),
                "-pass", "env:BACKUP_PASSPHRASE",
            ],
            check=True,
            capture_output=True,
        )
        return destination.stat().st_size
    finally:
        plain.unlink(missing_ok=True)


def _client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=_env("R2_ENDPOINT"),
        aws_access_key_id=_env("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_env("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def upload(client, bucket: str, key: str, path: Path) -> None:
    client.upload_file(str(path), bucket, key)


def prune(client, bucket: str, prefix: str, keep: int) -> list:
    """Delete the oldest archives beyond ``keep``; return the removed keys."""
    listing = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    keys = sorted(
        (item["Key"] for item in listing.get("Contents", [])),
        reverse=True,
    )
    stale = [key for key in keys if key.endswith(".tar.gz.enc")][keep:]
    for key in stale:
        client.delete_object(Bucket=bucket, Key=key)
    return stale


def main() -> int:
    missing = missing_configuration()
    if missing:
        print(f"backup: missing configuration: {', '.join(missing)}", file=sys.stderr)
        return 2

    sources = [part.strip() for part in _env("BACKUP_SOURCES", "/app/config,/app/logs").split(",") if part.strip()]
    prefix = _env("BACKUP_PREFIX", "backups").strip("/")
    keep = int(_env("BACKUP_KEEP", "14") or 14)
    name = archive_name()
    key = f"{prefix}/{name}"

    with tempfile.TemporaryDirectory() as workdir:
        encrypted = Path(workdir) / name
        size = build_archive(sources, encrypted)
        client = _client()
        upload(client, _env("R2_BUCKET"), key, encrypted)

    removed = prune(client, _env("R2_BUCKET"), f"{prefix}/", keep)
    print(f"backup: uploaded {key} ({size} bytes); pruned {len(removed)} old archive(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
