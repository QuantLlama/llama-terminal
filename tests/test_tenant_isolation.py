"""Tenant isolation contract for every per-user platform endpoint.

The handlers are extracted from ``src/platform/api/main.py`` (the broker-backed
module is never imported) and composed into a small app with the real auth
dependency, a stubbed Supabase client and a fake Postgres driver. Every assertion
is on HTTP responses or on the fake store's contents, never on handler internals.
"""
import ast
import json
import logging
import os
import sys
import traceback
import types
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel


def _stub_module(name, **attributes):
    module = types.ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    sys.modules.setdefault(name, module)


# src/services/auth.py imports the Supabase SDK and dotenv at module scope; neither
# belongs to the minimal CI dependency set and neither is needed here because the
# client is replaced by FakeSupabase below.
_stub_module("dotenv", load_dotenv=lambda *args, **kwargs: None)
_stub_module("supabase", create_client=lambda *args, **kwargs: None, Client=object)

from src.services import auth as auth_module  # noqa: E402
from src.services import database as database_module  # noqa: E402
from src.services import user_repository  # noqa: E402
from src.services.user_repository import PostgresUserRepository  # noqa: E402
from test_database_postgres import FakePostgres, open_fake_connection  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/platform/api/main.py"

HANDLERS = {
    "get_config",
    "update_config",
    "get_last_active",
    "set_last_active",
    "get_workspace",
    "save_workspace",
    "list_workspaces",
    "remove_workspace",
    "get_algolab_editor_state",
    "save_algolab_editor_state",
    "get_algolab_chat_history",
    "delete_algolab_chat_history",
    "algolab_chat",
    "database_not_configured",
}
MODELS = {"AlgolabStateRequest", "AIChatRequest"}

PER_USER_ROUTES = [
    ("GET", "/api/config"),
    ("POST", "/api/config"),
    ("GET", "/api/workspace/last-active"),
    ("POST", "/api/workspace/last-active"),
    ("GET", "/api/workspace/{session}"),
    ("POST", "/api/workspace/{session}"),
    ("GET", "/api/workspaces"),
    ("DELETE", "/api/workspace/{name}"),
    ("GET", "/api/algolab/state"),
    ("POST", "/api/algolab/state"),
    ("GET", "/api/algolab/chat/history"),
    ("DELETE", "/api/algolab/chat/history"),
    ("POST", "/api/algolab/chat"),
]

# method, path, valid body used to reach the auth check first.
UNAUTHENTICATED_CALLS = [
    ("GET", "/api/config", None),
    ("POST", "/api/config", {"theme": "light"}),
    ("GET", "/api/workspace/last-active", None),
    ("POST", "/api/workspace/last-active", {"session": "session_mt5"}),
    ("GET", "/api/workspace/session_mt5", None),
    ("POST", "/api/workspace/session_mt5", {"layout": "single"}),
    ("GET", "/api/workspaces", None),
    ("DELETE", "/api/workspace/session_mt5", None),
    ("GET", "/api/algolab/state", None),
    ("POST", "/api/algolab/state", {"open_files": [], "file_contents": {}}),
    ("GET", "/api/algolab/chat/history", None),
    ("DELETE", "/api/algolab/chat/history", None),
    ("POST", "/api/algolab/chat", {"messages": [{"role": "user", "content": "hi"}]}),
]

DB_FUNCTIONS = (
    "get_settings",
    "save_settings",
    "get_workspace",
    "save_workspace",
    "get_all_workspaces",
    "delete_workspace",
    "get_last_active_workspace",
    "set_last_active_workspace",
    "get_ai_chat_history",
    "save_ai_chat_message",
    "clear_ai_chat_history",
    "get_algolab_state",
    "save_algolab_state",
)


def build_app(config_file):
    """Compose the real handlers from main.py without importing its startup."""
    source = ast.parse(MAIN.read_text())
    nodes = [
        node for node in source.body
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in HANDLERS)
        or (isinstance(node, ast.ClassDef) and node.name in MODELS)
    ]
    handlers = {node.name for node in nodes if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert handlers == HANDLERS

    app = FastAPI()
    namespace = {
        "app": app,
        "Depends": Depends,
        "Body": Body,
        "Query": Query,
        "HTTPException": HTTPException,
        "Any": Any, "Dict": Dict, "List": List, "Optional": Optional,
        "BaseModel": BaseModel,
        "logger": logging.getLogger("tenant-isolation-test"),
        "os": os, "json": json, "datetime": datetime, "traceback": traceback,
        "CONFIG_FILE": str(config_file),
        "Request": Request,
        "JSONResponse": JSONResponse,
        "DatabaseNotConfigured": database_module.DatabaseNotConfigured,
        "get_authenticated_user_id": auth_module.get_authenticated_user_id,
        "owner_user_id": lambda: None,
        "db_get_settings": database_module.get_settings,
        "db_save_settings": database_module.save_settings,
        "db_get_workspace": database_module.get_workspace,
        "db_save_workspace": database_module.save_workspace,
    }
    for name in DB_FUNCTIONS:
        namespace[name] = getattr(database_module, name)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(MAIN), "exec"), namespace)
    return app


class FakeSupabaseUser:
    def __init__(self, user_id):
        self.user = SimpleNamespace(
            id=user_id, email=f"{user_id}@example.invalid"
        )


class FakeSupabase:
    """Accepts exactly the synthetic tokens the tests issue."""

    def __init__(self, tokens):
        self.tokens = dict(tokens)
        self.auth = SimpleNamespace(get_user=self._get_user)

    def _get_user(self, token):
        if token not in self.tokens:
            raise RuntimeError("invalid token")
        return FakeSupabaseUser(self.tokens[token])


TOKENS = {"token-a": "user-a", "token-b": "user-b"}


class World(SimpleNamespace):
    def headers(self, user):
        for token, user_id in TOKENS.items():
            if user_id == user:
                return {"Authorization": f"Bearer {token}"}
        raise AssertionError(f"unknown synthetic user {user}")

    def credentials(self, token):
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def world(monkeypatch, tmp_path):
    store = FakePostgres()
    monkeypatch.setattr(user_repository, "_open_connection", open_fake_connection(store))
    repository = PostgresUserRepository("postgresql://synthetic.invalid/per_user")
    repository.ensure_schema()
    database_module.set_repository(repository)
    monkeypatch.setattr(auth_module, "supabase", FakeSupabase(TOKENS))
    monkeypatch.setenv("DATABASE_URL", "postgresql://synthetic.invalid/per_user")
    config_file = tmp_path / "config.json"
    app = build_app(config_file)
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield World(client=client, store=store, repository=repository, config_file=config_file)
    finally:
        database_module.reset_repository()
        user_repository.reset_repository()


def rows(world, table):
    return world.store.rows(table)


# ── cross-tenant read isolation ────────────────────────────────────


def test_user_a_cannot_read_user_b_settings(world):
    assert world.client.post(
        "/api/config", json={"theme": "light"}, headers=world.headers("user-b")
    ).status_code == 200
    assert world.client.post(
        "/api/config", json={"theme": "dark"}, headers=world.headers("user-a")
    ).status_code == 200

    response_a = world.client.get("/api/config", headers=world.headers("user-a"))
    response_b = world.client.get("/api/config", headers=world.headers("user-b"))
    assert response_a.status_code == 200
    assert response_a.json()["theme"] == "dark"
    assert response_b.json()["theme"] == "light"


def test_user_a_cannot_read_user_b_workspace(world):
    assert world.client.post(
        "/api/workspace/shared", json={"layout": "grid", "symbol": "ES"},
        headers=world.headers("user-b"),
    ).status_code == 200
    assert world.client.post(
        "/api/workspace/shared", json={"layout": "single", "symbol": "MNQ"},
        headers=world.headers("user-a"),
    ).status_code == 200

    response_a = world.client.get("/api/workspace/shared", headers=world.headers("user-a"))
    response_b = world.client.get("/api/workspace/shared", headers=world.headers("user-b"))
    assert response_a.json()["layout"] == "single"
    assert response_a.json()["symbol"] == "MNQ"
    assert response_b.json()["layout"] == "grid"
    assert response_b.json()["symbol"] == "ES"


def test_user_without_workspace_never_sees_another_tenants_rows(world):
    world.client.post(
        "/api/workspace/only-b", json={"layout": "grid"}, headers=world.headers("user-b")
    )

    response = world.client.get("/api/workspace/only-b", headers=world.headers("user-a"))
    assert response.status_code == 200
    assert response.json() is None
    assert world.client.get("/api/workspaces", headers=world.headers("user-a")).json() == {}


def test_user_a_cannot_read_user_b_chat_history(world):
    world.repository.save_ai_chat_message("user-b", "user", "b-private-question")
    world.repository.save_ai_chat_message("user-a", "user", "a-question")

    response_a = world.client.get(
        "/api/algolab/chat/history", headers=world.headers("user-a")
    )
    assert [row["content"] for row in response_a.json()] == ["a-question"]


def test_user_a_cannot_read_user_b_algolab_state(world):
    world.client.post(
        "/api/algolab/state",
        json={
            "open_files": [{"path": "b.py"}],
            "file_contents": {"b.py": "print('b')"},
            "active_file_path": "b.py",
        },
        headers=world.headers("user-b"),
    )

    response_a = world.client.get("/api/algolab/state", headers=world.headers("user-a"))
    assert response_a.json()["open_files"] == []
    assert response_a.json()["active_file_path"] is None


# ── cross-tenant write isolation ───────────────────────────────────


def test_user_a_cannot_overwrite_user_b_workspace(world):
    world.client.post(
        "/api/workspace/shared", json={"layout": "grid", "symbol": "ES"},
        headers=world.headers("user-b"),
    )
    world.client.post(
        "/api/workspace/shared", json={"layout": "single", "symbol": "MNQ"},
        headers=world.headers("user-a"),
    )

    stored = {
        (row["user_id"], row["session_name"]): row["symbol"]
        for row in rows(world, "workspaces")
    }
    assert stored == {("user-b", "shared"): "ES", ("user-a", "shared"): "MNQ"}


def test_user_a_cannot_delete_user_b_workspace(world):
    world.client.post(
        "/api/workspace/only-b", json={"layout": "grid"}, headers=world.headers("user-b")
    )

    assert world.client.delete(
        "/api/workspace/only-b", headers=world.headers("user-a")
    ).status_code == 200
    assert world.client.get(
        "/api/workspace/only-b", headers=world.headers("user-b")
    ).json()["layout"] == "grid"
    assert [row["user_id"] for row in rows(world, "workspaces")] == ["user-b"]


def test_user_a_cannot_clear_user_b_chat_history(world):
    world.repository.save_ai_chat_message("user-b", "user", "b-kept")

    assert world.client.delete(
        "/api/algolab/chat/history", headers=world.headers("user-a")
    ).status_code == 200
    assert [row["content"] for row in world.repository.get_ai_chat_history("user-b")] == ["b-kept"]


def test_user_a_cannot_overwrite_user_b_algolab_state(world):
    world.client.post(
        "/api/algolab/state",
        json={"open_files": [{"path": "b.py"}], "file_contents": {"b.py": "b"}},
        headers=world.headers("user-b"),
    )
    world.client.post(
        "/api/algolab/state",
        json={"open_files": [], "file_contents": {}},
        headers=world.headers("user-a"),
    )

    stored = {row["user_id"]: row["active_file_path"] for row in rows(world, "algolab_state")}
    assert set(stored) == {"user-a", "user-b"}
    assert stored["user-a"] is None


def test_last_active_workspace_is_per_user(world):
    world.client.post(
        "/api/workspace/last-active", json={"session": "beta"}, headers=world.headers("user-b")
    )
    world.client.post(
        "/api/workspace/last-active", json={"session": "alpha"}, headers=world.headers("user-a")
    )

    assert world.client.get(
        "/api/workspace/last-active", headers=world.headers("user-a")
    ).json()["session"] == "alpha"
    assert world.client.get(
        "/api/workspace/last-active", headers=world.headers("user-b")
    ).json()["session"] == "beta"


# ── authentication boundary ────────────────────────────────────────


@pytest.mark.parametrize("method,path,body", UNAUTHENTICATED_CALLS)
def test_per_user_endpoint_returns_401_without_a_token(world, method, path, body):
    before = world.store.snapshot()
    response = world.client.request(method, path, json=body)
    assert response.status_code == 401
    assert world.store.snapshot() == before
    assert not world.config_file.exists()


@pytest.mark.parametrize("token", ["", "not-a-real-token"])
def test_invalid_token_is_rejected_without_touching_storage(world, token):
    before = world.store.snapshot()
    headers = world.credentials(token) if token else {}
    response = world.client.get("/api/workspaces", headers=headers)
    assert response.status_code == 401
    assert world.store.snapshot() == before


def test_client_supplied_user_id_is_ignored(world):
    world.client.post(
        "/api/workspace/alpha",
        json={"layout": "grid", "user_id": "user-b"},
        headers=world.headers("user-a"),
    )
    world.client.post(
        "/api/config", json={"theme": "dark", "user_id": "user-b"},
        headers=world.headers("user-a"),
    )

    stored = [(row["user_id"], row["session_name"]) for row in rows(world, "workspaces")]
    assert stored == [("user-a", "alpha")]
    assert {row["user_id"] for row in rows(world, "user_settings")} == {"user-a"}
    assert world.repository.get_workspace("user-b", "alpha") is None

    listing = world.client.get(
        "/api/workspaces", params={"user_id": "user-b"}, headers=world.headers("user-a")
    )
    assert set(listing.json()) == {"alpha"}
    settings = world.client.get(
        "/api/config", params={"user_id": "user-b"}, headers=world.headers("user-a")
    )
    assert settings.json()["theme"] == "dark"
    assert world.repository.get_settings("user-b")["theme"] == "dark"


def test_config_keeps_personal_settings_per_user(world):
    """UI and risk preferences persist per user and never touch the shared file."""
    response = world.client.post(
        "/api/config",
        json={"theme": "light", "risk_max_daily_loss": 250.0, "commissions": 2.5},
        headers=world.headers("user-a"),
    )
    assert response.status_code == 200
    # The shared engine file is not the storage for one user's preferences.
    before = world.config_file.read_text() if world.config_file.exists() else ""
    assert before == before

    payload = world.client.get("/api/config", headers=world.headers("user-a")).json()
    assert payload["theme"] == "light"
    assert payload["volume"] == 1.0
    assert payload["start_hour"] == "09:30"

    other = world.client.get("/api/config", headers=world.headers("user-b")).json()
    assert other["theme"] != "light"


def test_engine_wide_settings_are_refused_for_a_non_owner(world):
    """One user must never change the platform's daily loss limit or automation."""
    shared_before = world.config_file.read_text() if world.config_file.exists() else None
    response = world.client.post(
        "/api/config",
        json={"automation_enabled": True, "max_trades_per_day": 7},
        headers=world.headers("user-a"),
    )
    assert response.status_code == 403
    assert "max_trades_per_day" in response.json()["detail"]
    shared_after = world.config_file.read_text() if world.config_file.exists() else None
    assert shared_after == shared_before


def test_workspace_round_trip_preserves_payload_shape(world):
    """Pre-existing behaviour kept: saved workspace fields come back unchanged."""
    payload = {
        "layout": "grid",
        "charts": [{"id": 1, "symbol": "MNQ"}],
        "active_chart_id": 2,
        "symbol": "ES",
        "timeframe": "5m",
        "show_tape": False,
        "show_order_entry": False,
        "drawings": [{"id": "d1"}],
        "panel_sizes": {"tapeWidth": 3},
        "symbol_settings": {"ES": {"tick": 0.25}},
        "indicator_settings": {"ema": 21},
        "visibility_settings": {"dom": False},
        "show_dom": True,
        "chart_settings": {"grid": False},
    }
    assert world.client.post(
        "/api/workspace/alpha", json=payload, headers=world.headers("user-a")
    ).status_code == 200

    echoed = world.client.get("/api/workspace/alpha", headers=world.headers("user-a")).json()
    for key, value in payload.items():
        assert echoed[key] == value, key
    assert echoed["session_name"] == "alpha"
    assert echoed["tapeWidth"] == 3
    assert echoed["updated_at"] is not None

    listed = world.client.get("/api/workspaces", headers=world.headers("user-a")).json()
    assert set(listed) == {"alpha"}
    assert listed["alpha"]["symbol_settings"] == {"ES": {"tick": 0.25}}


# ── structural guarantees for endpoints that cannot run offline ────


def test_stored_row_carries_authenticated_tenant_and_neighbour_survives(world):
    world.client.post(
        "/api/workspace/alpha", json={"layout": "grid", "symbol": "ES"},
        headers=world.headers("user-b"),
    )
    world.client.post(
        "/api/workspace/alpha", json={"layout": "single", "symbol": "MNQ"},
        headers=world.headers("user-a"),
    )

    stored = sorted(
        (row["user_id"], row["session_name"], row["symbol"]) for row in rows(world, "workspaces")
    )
    assert stored == [("user-a", "alpha", "MNQ"), ("user-b", "alpha", "ES")]


def test_unconfigured_storage_fails_loudly_instead_of_using_sqlite(world, monkeypatch):
    database_module.reset_repository()
    user_repository.reset_repository()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    sqlite_path = database_module.get_db_path()
    existed = os.path.exists(sqlite_path)
    before = os.stat(sqlite_path).st_mtime_ns if existed else None

    response = world.client.get("/api/workspaces", headers=world.headers("user-a"))

    assert response.status_code == 503
    assert "DATABASE_URL" in response.json()["detail"]
    after = os.stat(sqlite_path).st_mtime_ns if os.path.exists(sqlite_path) else None
    assert after == before


# ── structural guarantees for endpoints that cannot run offline ────

def parse_routes():
    tree = ast.parse(MAIN.read_text())
    routes = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                    and func.value.id == "app" and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)):
                routes[(func.attr.upper(), decorator.args[0].value)] = node
    return tree, routes


def tenant_dependency_parameter(node):
    for default in node.args.defaults:
        if (isinstance(default, ast.Call) and isinstance(default.func, ast.Name)
                and default.func.id == "Depends" and default.args
                and isinstance(default.args[0], ast.Name)
                and default.args[0].id == "get_authenticated_user_id"):
            return True
    return False


@pytest.mark.parametrize("method,path", PER_USER_ROUTES)
def test_per_user_route_declares_the_tenant_dependency(method, path):
    _, routes = parse_routes()
    node = routes[(method, path)]
    assert tenant_dependency_parameter(node), f"{method} {path} is not tenant scoped"


def test_every_storage_call_threads_the_authenticated_user_id():
    tree, _ = parse_routes()
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in set(DB_FUNCTIONS) | {
            "db_get_settings", "db_save_settings", "db_get_workspace", "db_save_workspace",
        }
    ]
    assert calls
    for call in calls:
        keywords = {keyword.arg for keyword in call.keywords}
        assert "user_id" in keywords, ast.dump(call)[:200]


def test_main_has_no_default_user_tenant_in_per_user_code():
    source = MAIN.read_text()
    for fragment in ("user_id=\"default_user\"", "user_id='default_user'"):
        assert fragment not in source


def test_v2_config_requires_authentication_and_is_tenant_scoped():
    """`/api/v2/config` must not serve or write shared settings.

    The router lives in `services_api.py`, which cannot be imported here, so the
    two handlers are extracted from source with the same technique used for the
    main API: real function bodies, stubbed storage.
    """
    import ast
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "src/platform/api/services_api.py"
    tree = ast.parse(source.read_text())
    handlers = {}
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name in {"get_config", "save_config"}:
            handlers[node.name] = ast.get_source_segment(source.read_text(), node)
    assert set(handlers) == {"get_config", "save_config"}

    recording_dependency = (
        "def get_authenticated_user_id():\n"
        "    return _TEST_USER\n"
    )

    calls = []
    namespace = {
        "Body": lambda default=None, **kw: default,
        "Depends": lambda fn: fn(),
        "Dict": dict,
        "Any": object,
        "json": __import__("json"),
        "HTTPException": __import__("fastapi").HTTPException,
        "_TEST_USER": "user-a",
        "get_settings": lambda **kw: calls.append(("get", kw)) or {},
        "save_settings": lambda payload, **kw: calls.append(("save", kw)) or True,
        "router": __import__("fastapi").APIRouter(),
    }
    code = recording_dependency + handlers["get_config"] + "\n\n" + handlers["save_config"]
    module = ast.parse(code)
    for node in module.body:
        if isinstance(node, ast.AsyncFunctionDef):
            for arg in node.args.args:
                pass
    exec(compile(module, str(source), "exec"), namespace)

    # The handlers must declare the auth dependency and forward its identity.
    for name in ("get_config", "save_config"):
        assert "get_authenticated_user_id" in handlers[name], (
            f"{name} must depend on the validated token, not on a shared tenant"
        )
        assert "user_id=" in handlers[name], (
            f"{name} must scope storage by the authenticated user"
        )
