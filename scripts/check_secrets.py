#!/usr/bin/env python3
"""Fail when a credential or a private identifier is committed.

The repository must never carry an exchange API key, a broker account number, an
authentication token or a personal absolute path. `.gitignore` prevents new files from
being tracked; this guard covers the case a human bypasses it (or pastes a key into an
existing file), which is how credentials actually leak.

Usage:
    python scripts/check_secrets.py            # scan the tracked tree
    python scripts/check_secrets.py --all      # scan every file, tracked or not
    python scripts/check_secrets.py --path DIR # scan an arbitrary directory

Exit code 0 when clean, 1 when anything matches.

The matched value is never printed, only a masked prefix: a report must not become the
leak it warns about.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Files that legitimately contain the patterns below (this guard and its fixtures).
ALLOWLIST_PATHS = {
    "scripts/check_secrets.py",
    "tests/test_secrets_guard.py",
}

SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".ttf", ".mp3",
    ".so", ".jsc", ".db", ".pyc", ".pdf", ".zip", ".whl",
}

# Vendored libraries and generated lock files: not first-party code, and their
# syntax definitions contain hundreds of "token: ..." literals that are not secrets.
SKIP_GLOBS = (
    "src/platform/web/lib/",
    "node_modules/",
    "package-lock.json",
    "skills-lock.json",
)

MAX_BYTES = 400_000

# (name, severity, pattern)
PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("private-key", "critical", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws-access-key", "critical", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", "critical", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}")),
    ("github-pat", "critical", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}")),
    ("slack-token", "critical", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("google-api-key", "critical", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("openai-key", "critical", re.compile(r"\bsk-[A-Za-z0-9]{24,}")),
    ("jwt", "high", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    (
        "hardcoded-secret",
        "high",
        re.compile(
            r"(?i)\b(?:api[_-]?key|api[_-]?secret|secret|password|passwd|token)\b[\"']?\s*[:=]\s*"
            r"[\"'][^\"'\s]{19,}[\"']"
        ),
    ),
    ("broker-account", "high", re.compile(r"(?i)\"(?:login|account_number|account)\"\s*:\s*\"\d{5,}\"")),
    ("personal-path", "low", re.compile(r"/home/[a-z0-9_.-]+/|C:\\\\Users\\\\[A-Za-z0-9_. -]+")),
]


def mask(value: str) -> str:
    value = value.strip()
    if len(value) <= 8:
        return value[:2] + "…"
    return value[:6] + "…" + f"({len(value)} chars)"


def candidate_files(root: Path, all_files: bool) -> list[Path]:
    if all_files or not (root / ".git").exists():
        return [p for p in root.rglob("*") if p.is_file()]
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout.split("\0")
    return [root / name for name in listed if name]


def scan_file(path: Path, root: Path) -> list[tuple[str, str, int, str]]:
    if path.suffix.lower() in SKIP_EXTENSIONS or not path.is_file():
        return []
    try:
        if path.stat().st_size > MAX_BYTES:
            return []
    except OSError:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    findings = []
    for name, severity, pattern in PATTERNS:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append((name, severity, line, match.group(0)))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reject committed secrets.")
    parser.add_argument("--path", type=Path, default=REPO_ROOT, help="directory to scan")
    parser.add_argument("--all", action="store_true", help="scan untracked files too")
    args = parser.parse_args(argv)

    root = args.path.resolve()
    findings: list[tuple[str, str, Path, int, str]] = []

    for path in candidate_files(root, args.all):
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if relative in ALLOWLIST_PATHS:
            continue
        if any(relative.startswith(glob) or relative.endswith(glob.strip("/")) for glob in SKIP_GLOBS):
            continue
        for name, severity, line, value in scan_file(path, root):
            findings.append((name, severity, Path(relative), line, value))

    if findings:
        findings.sort(key=lambda f: (f[1] != "critical", f[1] != "high", str(f[2]), f[3]))
        print(f"{len(findings)} potential secret(s) found:\n", file=sys.stderr)
        for name, severity, relative, line, value in findings:
            print(f"  [{severity}] {relative}:{line}  {name}  {mask(value)}", file=sys.stderr)
        print(
            "\nRemove the value, load it from the environment, and rotate the credential:\n"
            "a secret that reached a commit is compromised even if a later commit deletes it.",
            file=sys.stderr,
        )
        return 1

    print(f"no secrets found ({len(candidate_files(root, args.all))} files scanned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
