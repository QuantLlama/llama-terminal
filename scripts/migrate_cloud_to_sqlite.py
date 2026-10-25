#!/usr/bin/env python3
"""Copy the cloud per-user rows into the local SQLite file, once and repeatably.

A local run reads its own SQLite file, so the rows the operator already created
in the cloud have to come across or the app starts empty. This script reads the
cloud PostgreSQL through ``DATABASE_URL`` (the tunnel) and writes the local file
that ``QLLAMA_STORAGE=sqlite`` serves.

What it copies, verbatim:

| Table | Upsert key |
| --- | --- |
| ``user_settings`` | ``user_id`` |
| ``algolab_state`` | ``user_id`` |
| ``workspaces`` | ``(user_id, session_name)`` |
| ``broker_accounts`` | ``(user_id, platform, account_id)`` |
| ``ai_chat_history`` | the whole message (role, content, skill, actions, timestamp) |

``credential_blob`` is copied unchanged and never printed: it is encrypted per
user with the installation master key, so the same ciphertext stays valid on the
same installation. Surrogate ``id`` values are not copied - SQLite assigns its
own - which is why a local file that already holds rows can be migrated into.

Idempotent: a second run inserts nothing. A row the cloud changed since the
previous run is updated; an unchanged row is skipped and counted as skipped.

Usage:
    DATABASE_URL=postgresql://... python scripts/migrate_cloud_to_sqlite.py
    python scripts/migrate_cloud_to_sqlite.py --sqlite-path config/quantum_llama.db

Exit codes: 0 copied, 2 no ``DATABASE_URL`` (nothing was touched).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.services.sqlite_user_repository import SqliteUserRepository  # noqa: E402
from src.services.user_repository import (  # noqa: E402
    ALGOLAB_COLUMNS,
    BROKER_ACCOUNT_COLUMNS,
    CHAT_COLUMNS,
    SETTINGS_COLUMNS,
    WORKSPACE_COLUMNS,
    DatabaseNotConfigured,
    PostgresUserRepository,
    database_url,
    sqlite_path,
)


@dataclass(frozen=True)
class TableSpec:
    """One copied table: its name, its row key and the columns kept verbatim."""

    name: str
    key: Tuple[str, ...]
    columns: Tuple[str, ...]


TABLE_SPECS: Tuple[TableSpec, ...] = (
    TableSpec("user_settings", ("user_id",), SETTINGS_COLUMNS),
    TableSpec("workspaces", ("user_id", "session_name"), WORKSPACE_COLUMNS),
    TableSpec(
        "ai_chat_history",
        ("user_id", "role", "content", "skill", "agent_actions", "timestamp"),
        CHAT_COLUMNS + ("timestamp",),
    ),
    TableSpec("algolab_state", ("user_id",), ALGOLAB_COLUMNS),
    TableSpec(
        "broker_accounts",
        ("user_id", "platform", "account_id"),
        BROKER_ACCOUNT_COLUMNS,
    ),
)


def _normalize(value: Any) -> Any:
    """JSON values arrive decoded from psycopg2 and as text from sqlite3."""
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def _same(stored: Any, incoming: Any) -> bool:
    if stored is None or incoming is None:
        return stored is None and incoming is None
    if isinstance(stored, float) or isinstance(incoming, float):
        try:
            return float(stored) == float(incoming)
        except (TypeError, ValueError):
            return False
    return stored == incoming


def _copy_table(source_cursor, target_cursor, spec: TableSpec) -> Dict[str, int]:
    """Copy one table row by row, upserting on its key and never on its id."""
    counts = {"inserted": 0, "updated": 0, "skipped": 0}
    column_list = ", ".join(spec.columns)
    placeholder_list = ", ".join(f":{column}" for column in spec.columns)
    # NULL-safe match: a message whose skill or actions are absent still keys.
    key_clause = " AND ".join(f"{column} IS :{column}" for column in spec.key)
    assignments = ", ".join(
        f"{column} = :{column}" for column in spec.columns if column not in spec.key
    )

    source_cursor.execute(f"SELECT {column_list} FROM {spec.name} ORDER BY id ASC")
    for row in source_cursor.fetchall():
        values = {column: _normalize(row.get(column)) for column in spec.columns}
        key_values = {column: values[column] for column in spec.key}
        existing = target_cursor.execute(
            f"SELECT {column_list} FROM {spec.name} WHERE {key_clause}", key_values
        ).fetchone()

        if existing is None:
            target_cursor.execute(
                f"INSERT INTO {spec.name} ({column_list}) VALUES ({placeholder_list})",
                values,
            )
            counts["inserted"] += 1
            continue
        if all(_same(existing[column], values[column]) for column in spec.columns):
            counts["skipped"] += 1
            continue
        target_cursor.execute(
            f"UPDATE {spec.name} SET {assignments} WHERE {key_clause}", values
        )
        counts["updated"] += 1
    return counts


def migrate_cloud_to_sqlite(source, target) -> Dict[str, Dict[str, int]]:
    """Copy every per-user table from *source* into the *target* SQLite store."""
    target.ensure_schema()
    counts: Dict[str, Dict[str, int]] = {}
    with source._cursor() as source_cursor, target._cursor() as target_cursor:
        for spec in TABLE_SPECS:
            counts[spec.name] = _copy_table(source_cursor, target_cursor, spec)
    return counts


def format_report(counts: Dict[str, Dict[str, int]]) -> str:
    """Per-table counts only: no row value, and never a credential blob."""
    lines = [
        f"{name:<24} inserted={counts[name]['inserted']} "
        f"updated={counts[name]['updated']} skipped={counts[name]['skipped']}"
        for name in counts
    ]
    totals = {
        action: sum(value[action] for value in counts.values())
        for action in ("inserted", "updated", "skipped")
    }
    lines.append(
        f"{'total':<24} inserted={totals['inserted']} "
        f"updated={totals['updated']} skipped={totals['skipped']}"
    )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy the cloud per-user rows into the local SQLite file."
    )
    parser.add_argument(
        "--sqlite-path",
        default=None,
        help="local file to write (default: $QLLAMA_SQLITE_PATH or config/quantum_llama.db)",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="cloud DSN to read (default: $DATABASE_URL)",
    )
    args = parser.parse_args(argv)

    try:
        source_url = (args.database_url or database_url()).strip()
    except DatabaseNotConfigured as error:
        print(f"[migrate] {error}", file=sys.stderr)
        return 2

    target_path = args.sqlite_path or sqlite_path()
    print(f"[migrate] reading the cloud rows and writing {target_path}")

    counts = migrate_cloud_to_sqlite(
        PostgresUserRepository(source_url), SqliteUserRepository(target_path)
    )
    print(format_report(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
