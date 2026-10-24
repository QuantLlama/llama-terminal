"""Contract tests for the served favicon.

Browsers request /favicon.ico directly. The SPA catch-all in
src/platform/api/main.py serves files from the web directory and falls back to
index.html, so the icon must exist there or the browser receives HTML.
"""

import os
import re

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "platform", "web")
INDEX_HTML = os.path.join(WEB_DIR, "index.html")


def test_favicon_file_exists_in_web_root():
    favicon = os.path.join(WEB_DIR, "favicon.ico")

    assert os.path.isfile(favicon), "src/platform/web/favicon.ico must ship with the app"
    with open(favicon, "rb") as handle:
        header = handle.read(4)
    # ICO files start with 00 00 01 00; PNG fallback files start with the PNG signature.
    assert header == b"\x00\x00\x01\x00" or header.startswith(b"\x89PNG"), (
        f"unexpected favicon header: {header!r}"
    )


def test_index_declares_the_favicon():
    with open(INDEX_HTML, encoding="utf-8", errors="ignore") as handle:
        html = handle.read()

    assert re.search(r'<link[^>]+rel="icon"[^>]+href="/favicon\.ico"', html), (
        "index.html must declare /favicon.ico as an icon link"
    )
