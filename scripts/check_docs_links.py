#!/usr/bin/env python3
"""Validate relative links in the repository's Markdown files.

The documentation is the product's front door: a dead link is a dead end for a
reader. This check runs in CI and fails on the first broken relative link.

Rules:
  - only relative links are checked; absolute URLs are another network's problem
  - anchors (``#section``) are ignored
  - fenced code blocks and inline code are skipped
  - a link target may be a file or a directory

Exit code 0 when every link resolves, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Markdown files that face a reader. Vendored skills and archived specs are not
# part of the product documentation.
SKIP_DIRS = {
    ".git",
    "node_modules",
    "venv",
    "venv_linux",
    "venv_agent",
    "build",
    "dist",
    "outputs",
    ".agents",
    ".claude",
    ".junie",
    ".openclaw",
    ".atl",
    ".codegraph",
    ".pytest_cache",
    "scratch",
}

LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def markdown_files() -> list[Path]:
    files = []
    for path in REPO_ROOT.rglob("*.md"):
        relative = path.relative_to(REPO_ROOT)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        files.append(path)
    return sorted(files)


def links_in(text: str) -> list[tuple[int, str]]:
    links: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in LINK_RE.finditer(line):
            links.append((number, match.group(1).strip()))
    return links


def is_checkable(target: str) -> bool:
    if not target or target.startswith("#"):
        return False
    lowered = target.lower()
    return not lowered.startswith(("http://", "https://", "mailto:", "tel:", "ftp:", "data:"))


def resolve(source: Path, target: str) -> Path | None:
    path_part = target.split("#", 1)[0].strip()
    if not path_part:
        return None
    if path_part.startswith("/"):
        return REPO_ROOT / path_part.lstrip("/")
    return (source.parent / path_part).resolve()


def main() -> int:
    broken: list[str] = []
    checked = 0
    files = markdown_files()

    for source in files:
        text = source.read_text(encoding="utf-8", errors="replace")
        for line, target in links_in(text):
            if not is_checkable(target):
                continue
            checked += 1
            destination = resolve(source, target)
            if destination is None or not destination.exists():
                broken.append(
                    f"{source.relative_to(REPO_ROOT)}:{line}: {target} -> "
                    f"{destination or 'unresolved'}"
                )

    print(f"checked {checked} relative links in {len(files)} markdown files")
    if broken:
        print(f"\n{len(broken)} broken link(s):", file=sys.stderr)
        for entry in broken:
            print(f"  {entry}", file=sys.stderr)
        return 1
    print("all relative links resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
