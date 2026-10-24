"""Engine-wide trading settings must not be writable by any authenticated user.

`POST /api/config` used to write every non-UI key straight into the shared
`src/config/live_config.json`, so any logged-in user could change the platform's
daily loss limit, volume or automation flag for everybody.
"""
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config_module(tmp_path, monkeypatch):
    """Import the real handler bodies with storage and auth stubbed."""
    import ast

    source = ROOT / "src/platform/api/main.py"
    text = source.read_text()
    tree = ast.parse(text)
    needed = {"get_config", "update_config"}
    segments = {}
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name in needed:
            segments[node.name] = ast.get_source_segment(text, node)
    assert set(segments) == needed

    calls = {"saved": [], "global": []}
    live = tmp_path / "live_config.json"
    live.write_text(json.dumps({"automation_enabled": False, "max_daily_loss": 500.0}))

    class _NotConfigured(Exception):
        pass

    ns = {
        "Body": lambda default=None, **kw: default,
        "Depends": lambda fn: fn(),
        "Dict": dict,
        "Any": object,
        "json": json,
        "os": __import__("os"),
        "HTTPException": __import__("fastapi").HTTPException,
        "DatabaseNotConfigured": _NotConfigured,
        "CONFIG_FILE": str(live),
        "logger": types.SimpleNamespace(info=lambda *a, **k: None,
                                        warning=lambda *a, **k: None,
                                        error=lambda *a, **k: None),
        "db_get_settings": lambda *, user_id: {},
        "db_save_settings": lambda data, *, user_id: calls["saved"].append((user_id, dict(data))),
        "owner_user_id": lambda: None,
        "get_authenticated_user_id": lambda: "user-a",
    }
    code = segments["get_config"] + "\n\n" + segments["update_config"]
    exec(compile(ast.parse(code), str(source), "exec"), ns)
    return ns, calls, live


def test_non_owner_cannot_change_engine_wide_trading_settings(config_module):
    ns, calls, live = config_module
    before = json.loads(live.read_text())
    with pytest.raises(Exception) as exc:
        # The handler is async; run it on a trivial event loop.
        import asyncio
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            ns["update_config"]({"max_daily_loss": 1.0, "volume": 99}, user_id="user-a")
        )
    detail = getattr(exc.value, "detail", str(exc.value))
    assert "max_daily_loss" in detail
    assert json.loads(live.read_text()) == before, "the shared file must be untouched"


def test_personal_ui_keys_still_save_per_user(config_module):
    ns, calls, live = config_module
    import asyncio
    before = json.loads(live.read_text())
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        ns["update_config"]({"theme": "light", "show_grid": False}, user_id="user-a")
    )
    assert calls["saved"] == [("user-a", {"theme": "light", "show_grid": False})]
    assert json.loads(live.read_text()) == before
