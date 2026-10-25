"""Tenant isolation for every accounts endpoint, asserted on HTTP responses.

The real handlers are extracted from ``src/platform/api/accounts_api.py`` and
composed into a small app with the real auth dependency, a stubbed Supabase
client, the real account managers, the real Postgres repository and a fake
DB-API driver. Assertions are on responses and on stored rows, never on handler
internals. Tradovate keeps its legacy single-file manager (out of scope for this
change) and is stubbed so no test reads or writes a worktree JSON file.
"""
import ast
import asyncio
import json
import logging
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel


def _stub_module(name, **attributes):
    module = types.ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    sys.modules.setdefault(name, module)


# src/services/auth.py imports the Supabase SDK and dotenv at module scope; the
# minimal CI dependency set has neither, and the client is replaced below.
_stub_module("dotenv", load_dotenv=lambda *args, **kwargs: None)
_stub_module("supabase", create_client=lambda *args, **kwargs: None, Client=object)

from src.services import auth as auth_module  # noqa: E402
from src.services import credential_manager  # noqa: E402
from src.services import database as database_module  # noqa: E402
from src.services import mt5_manager as mt5_manager_module  # noqa: E402
from src.services import ninjatrader_manager as nt8_manager_module  # noqa: E402
from src.services import user_repository  # noqa: E402
from src.services.crypto_manager import get_crypto_manager  # noqa: E402
from src.services.mt5_manager import get_manager  # noqa: E402
from src.services.ninjatrader_manager import get_nt8_manager  # noqa: E402
from src.services.user_repository import PostgresUserRepository  # noqa: E402
from test_database_postgres import FakePostgres, open_fake_connection  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ACCOUNTS_API = ROOT / "src/platform/api/accounts_api.py"

HANDLERS = {
    "get_accounts",
    "add_account",
    "update_account",
    "remove_account",
    "test_existing_account_connection",
    "set_master_account",
    "connect_account",
    "get_brokers",
    "set_leverage_account",
    "search_servers",
    "_account_manager",
    "_owned_account",
}
MODELS = {"AccountCreate", "AccountResponse", "AccountUpdate", "ConnectionTestResponse"}


# ── Supabase stand-in ──────────────────────────────────────────────


class FakeSupabaseUser:
    def __init__(self, user_id):
        self.user = SimpleNamespace(id=user_id, email=f"{user_id}@example.invalid")


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


class TradovateOutOfScope:
    """Tradovate still lives in a shared JSON file; this change does not own it."""

    platform = "tradovate"

    def get_accounts(self, **kwargs):
        return []

    def get_account(self, account_id, **kwargs):
        return None

    def add_account(self, **kwargs):
        raise AssertionError("tradovate create is out of scope for this change")

    def update_account(self, account_id, update_data, **kwargs):
        return None

    def remove_account(self, account_id, **kwargs):
        return False

    def set_master_account(self, account_id, **kwargs):
        return False


def _unavailable_connector(*args, **kwargs):
    return None


# ── app composition ────────────────────────────────────────────────


def _route_nodes():
    source = ACCOUNTS_API.read_text()
    tree = ast.parse(source)
    nodes = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    functions = {n.name for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert functions == HANDLERS, sorted(functions ^ HANDLERS)
    assert {n.name for n in nodes if isinstance(n, ast.ClassDef)} == MODELS
    return source, tree, nodes


def _json_response(request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


def build_app():
    """Execute the real handler bodies from accounts_api.py."""
    source, tree, nodes = _route_nodes()
    app = FastAPI()
    router = APIRouter(prefix="/api/accounts", tags=["Accounts"])
    namespace = {
        "app": app,
        "router": router,
        "APIRouter": APIRouter,
        "Depends": Depends,
        "Query": Query,
        "Body": Body,
        "HTTPException": HTTPException,
        "BaseModel": BaseModel,
        "Optional": Optional,
        "List": List,
        "Dict": Dict,
        "Any": Any,
        "logger": logging.getLogger("accounts-isolation-test"),
        "os": os,
        "asyncio": asyncio,
        "Request": Request,
        "JSONResponse": JSONResponse,
        "DatabaseNotConfigured": user_repository.DatabaseNotConfigured,
        "get_authenticated_user_id": auth_module.get_authenticated_user_id,
        "get_manager": get_manager,
        "get_crypto_manager": get_crypto_manager,
        "get_nt8_manager": get_nt8_manager,
        "get_tradovate_manager": lambda: TradovateOutOfScope(),
        "get_connector": _unavailable_connector,
        "get_tradovate_connector": _unavailable_connector,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ACCOUNTS_API), "exec"), namespace)
    app.include_router(router)
    app.add_exception_handler(user_repository.DatabaseNotConfigured, _json_response)
    return app


class World(SimpleNamespace):
    def headers(self, user):
        for token, user_id in TOKENS.items():
            if user_id == user:
                return {"Authorization": f"Bearer {token}"}
        raise AssertionError(f"unknown synthetic user {user}")

    def accounts(self):
        return self.store.rows("broker_accounts")


@pytest.fixture
def world(monkeypatch, tmp_path):
    store = FakePostgres()
    monkeypatch.setattr(user_repository, "_open_connection", open_fake_connection(store))
    repository = PostgresUserRepository("postgresql://synthetic.invalid/per_user")
    repository.ensure_schema()
    database_module.set_repository(repository)
    monkeypatch.setattr(auth_module, "supabase", FakeSupabase(TOKENS))
    monkeypatch.setenv("DATABASE_URL", "postgresql://synthetic.invalid/per_user")

    # Account files lived under project-root paths that are not mounted volumes;
    # nothing in these tests may create them.
    data_root = tmp_path / "data"
    monkeypatch.setattr(mt5_manager_module, "get_data_path", lambda *parts: str(data_root.joinpath(*parts)))
    monkeypatch.setattr(mt5_manager_module, "_manager", None)
    monkeypatch.setattr(nt8_manager_module, "_manager", None)
    monkeypatch.setenv(credential_manager.MASTER_KEY_ENV, "synthetic-installation-master-secret")
    credential_manager.reset_vault()

    client = TestClient(build_app(), raise_server_exceptions=False)
    try:
        yield World(
            client=client, store=store, repository=repository, data_root=data_root,
        )
    finally:
        database_module.reset_repository()
        user_repository.reset_repository()
        credential_manager.reset_vault()
        mt5_manager_module._manager = None
        nt8_manager_module._manager = None


MT5_CREATE = {
    "name": "AMP demo",
    "broker": "AMP",
    "platform": "mt5",
    "server": "AMPGlobalUSA-Demo",
    "login": "5001",
    "password": "synthetic-password",
    "account_type": "demo",
}

NT8_CREATE = {
    "name": "bridge",
    "broker": "NinjaTrader",
    "platform": "nt8",
    "exchange_dir": "/tmp/synthetic-exchange",
    "account_type": "demo",
}

CRYPTO_CREATE = {
    "name": "bybit",
    "broker": "bybit",
    "platform": "crypto",
    "api_key": "public-key",
    "api_secret": "synthetic-secret",
}


def create(client, payload, user):
    response = client.post("/api/accounts", json=payload, headers=headers_for(user))
    assert response.status_code == 200, response.text
    return response.json()


def headers_for(user):
    for token, user_id in TOKENS.items():
        if user_id == user:
            return {"Authorization": f"Bearer {token}"}
    raise AssertionError(user)


# ── cross-tenant reads ─────────────────────────────────────────────


def test_user_a_never_lists_user_b_accounts(world):
    created = create(world.client, MT5_CREATE, "user-b")

    listing_a = world.client.get("/api/accounts", headers=world.headers("user-a"))
    listing_b = world.client.get("/api/accounts", headers=world.headers("user-b"))

    assert listing_a.status_code == 200
    assert listing_a.json() == []
    assert [account["id"] for account in listing_b.json()] == [created["id"]]
    assert {row["user_id"] for row in world.accounts()} == {"user-b"}


def test_user_a_cannot_read_user_b_account_through_an_update(world):
    created = create(world.client, NT8_CREATE, "user-b")
    before = world.store.snapshot()

    response = world.client.patch(
        f"/api/accounts/{created['id']}",
        params={"platform": "nt8"},
        json={"name": "stolen"},
        headers=world.headers("user-a"),
    )

    assert response.status_code == 404
    assert world.store.snapshot() == before
    assert world.repository.get_account(
        user_id="user-b", platform="nt8", account_id=created["id"]
    )["metadata"]["name"] == "bridge"


def test_user_a_cannot_delete_user_b_account(world):
    created = create(world.client, MT5_CREATE, "user-b")
    before = world.store.snapshot()

    response = world.client.delete(
        f"/api/accounts/{created['id']}", headers=world.headers("user-a")
    )

    assert response.status_code == 404
    assert world.store.snapshot() == before
    assert world.client.get("/api/accounts", headers=world.headers("user-b")).json() != []


def test_user_a_cannot_overwrite_user_b_account(world):
    created = create(world.client, MT5_CREATE, "user-b")

    response = world.client.patch(
        f"/api/accounts/{created['id']}",
        json={"name": "overwritten"},
        headers=world.headers("user-a"),
    )
    assert response.status_code == 404
    assert world.repository.get_account(
        user_id="user-b", platform="mt5", account_id=created["id"]
    )["metadata"]["name"] == "AMP demo"


def test_user_a_cannot_connect_or_crown_user_b_account(world):
    created = create(world.client, MT5_CREATE, "user-b")
    before = world.store.snapshot()

    connect = world.client.post(
        f"/api/accounts/{created['id']}/connect", headers=world.headers("user-a")
    )
    master = world.client.post(
        f"/api/accounts/{created['id']}/master", headers=world.headers("user-a")
    )

    assert connect.status_code == 400
    assert master.status_code == 400
    assert world.store.snapshot() == before


def test_two_users_keep_the_same_account_id_apart(world):
    first = create(world.client, MT5_CREATE, "user-a")
    second = create(world.client, MT5_CREATE, "user-b")

    assert first["id"] == second["id"]
    assert len(world.accounts()) == 2
    assert sorted(row["user_id"] for row in world.accounts()) == ["user-a", "user-b"]


# ── authentication boundary ────────────────────────────────────────


ACCOUNT_ROUTES = [
    ("GET", "/api/accounts", None),
    ("POST", "/api/accounts", MT5_CREATE),
    ("PATCH", "/api/accounts/a1", {"name": "renamed"}),
    ("DELETE", "/api/accounts/a1", None),
    ("POST", "/api/accounts/a1/test", None),
    ("POST", "/api/accounts/a1/master", None),
    ("POST", "/api/accounts/a1/connect", None),
    ("GET", "/api/accounts/brokers", None),
    ("POST", "/api/accounts/a1/leverage", {"symbol": "BTC/USDT", "leverage": 5}),
    ("GET", "/api/accounts/server-search", None),
]


@pytest.mark.parametrize("method,path,body", ACCOUNT_ROUTES)
def test_every_accounts_route_requires_a_token(world, method, path, body):
    before = world.store.snapshot()
    response = world.client.request(method, path, params={"q": "AMP"}, json=body)
    assert response.status_code == 401
    assert world.store.snapshot() == before
    assert world.accounts() == []


@pytest.mark.parametrize("token", ["", "not-a-real-token"])
def test_invalid_token_is_rejected_without_touching_the_store(world, token):
    before = world.store.snapshot()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = world.client.post("/api/accounts", json=MT5_CREATE, headers=headers)
    assert response.status_code == 401
    assert world.store.snapshot() == before


def test_client_supplied_user_id_is_ignored(world):
    response = world.client.post(
        "/api/accounts",
        params={"user_id": "user-b"},
        json={**MT5_CREATE, "user_id": "user-b", "owner_id": "user-b"},
        headers=world.headers("user-a"),
    )
    assert response.status_code == 200, response.text

    assert {row["user_id"] for row in world.accounts()} == {"user-a"}
    assert world.client.get("/api/accounts", headers=world.headers("user-b")).json() == []
    assert world.repository.list_accounts(user_id="user-b") == []


# ── credential keys ────────────────────────────────────────────────


def test_credentials_stored_for_one_user_cannot_be_decrypted_for_another(world):
    create(world.client, MT5_CREATE, "user-a")
    create(world.client, {**MT5_CREATE, "password": "other-password"}, "user-b")

    blobs = {
        row["user_id"]: row["credential_blob"] for row in world.accounts()
    }
    assert blobs["user-a"] != blobs["user-b"]
    for blob in blobs.values():
        assert "synthetic-password" not in blob
        assert "other-password" not in blob

    vault = credential_manager.get_vault()
    assert json.loads(vault.manager_for("user-a").decrypt(blobs["user-a"])) == {
        "password": "synthetic-password"
    }
    assert vault.manager_for("user-b").decrypt(blobs["user-a"]) == "DECRYPTION_FAILED"
    assert vault.manager_for("user-a").decrypt(blobs["user-b"]) == "DECRYPTION_FAILED"


# ── missing database ───────────────────────────────────────────────


def test_missing_database_url_answers_503_instead_of_using_json_files(world, monkeypatch):
    database_module.reset_repository()
    user_repository.reset_repository()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    before = world.store.snapshot()

    response = world.client.get("/api/accounts", headers=world.headers("user-a"))

    assert response.status_code == 503
    assert "DATABASE_URL" in response.json()["detail"]
    assert world.store.snapshot() == before
    assert not (world.data_root / "src" / "config").exists(), "no JSON fallback file was created"


def test_missing_database_url_blocks_creation(world, monkeypatch):
    database_module.reset_repository()
    user_repository.reset_repository()
    monkeypatch.delenv("DATABASE_URL", raising=False)

    response = world.client.post(
        "/api/accounts", json=MT5_CREATE, headers=world.headers("user-a")
    )

    assert response.status_code == 503
    assert "DATABASE_URL" in response.json()["detail"]
    assert not (world.data_root / "src" / "config").exists()


# ── pre-existing behaviour kept ────────────────────────────────────


def test_account_listing_keeps_its_historical_shape(world):
    mt5 = create(world.client, MT5_CREATE, "user-a")
    nt8 = create(world.client, NT8_CREATE, "user-a")

    listing = world.client.get("/api/accounts", headers=world.headers("user-a")).json()
    by_platform = {account["platform"]: account for account in listing}

    assert set(by_platform) == {"mt5", "nt8"}
    assert by_platform["mt5"]["id"] == mt5["id"]
    assert by_platform["mt5"]["login"] == "5001"
    assert by_platform["mt5"]["status"] == "inactive"
    assert by_platform["mt5"]["is_master"] is False
    assert by_platform["nt8"]["exchange_dir"] == "/tmp/synthetic-exchange"
    assert by_platform["nt8"]["broker"] == "NinjaTrader"
    for account in listing:
        assert "password" not in account
        assert "api_secret" not in account


def test_duplicate_mt5_login_is_still_refused(world):
    create(world.client, MT5_CREATE, "user-a")
    response = world.client.post(
        "/api/accounts", json={**MT5_CREATE, "name": "second"}, headers=world.headers("user-a")
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Account already exists"
    assert len(world.accounts()) == 1


def test_master_account_selection_stays_per_user(world):
    first = create(world.client, MT5_CREATE, "user-a")
    second = create(
        world.client, {**MT5_CREATE, "login": "5002", "name": "second"}, "user-a"
    )
    other = create(world.client, MT5_CREATE, "user-b")

    assert world.client.post(
        f"/api/accounts/{first['id']}/master", headers=world.headers("user-a")
    ).status_code == 200

    stored = {
        (row["user_id"], row["account_id"]): json.loads(row["metadata"]).get("is_master")
        for row in world.accounts()
    }
    assert stored == {
        ("user-a", first["id"]): True,
        ("user-a", second["id"]): False,
        ("user-b", other["id"]): False,
    }


def test_update_and_delete_work_for_the_owner(world):
    created = create(world.client, MT5_CREATE, "user-a")

    updated = world.client.patch(
        f"/api/accounts/{created['id']}",
        json={"name": "renamed", "password": "rotated-password"},
        headers=world.headers("user-a"),
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "renamed"

    vault = credential_manager.get_vault()
    blob = world.repository.list_accounts(user_id="user-a")[0]["credential_blob"]
    assert json.loads(vault.manager_for("user-a").decrypt(blob)) == {
        "password": "rotated-password"
    }

    removed = world.client.delete(
        f"/api/accounts/{created['id']}", headers=world.headers("user-a")
    )
    assert removed.status_code == 200
    assert world.accounts() == []


def test_unknown_platform_is_rejected_with_400_and_stores_nothing(world):
    """Deliberate deviation: this used to answer 500 through a broad wrapper."""
    response = world.client.post(
        "/api/accounts",
        json={"name": "x", "broker": "y", "platform": "nope"},
        headers=world.headers("user-a"),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported platform: nope"
    assert world.accounts() == []


def test_crypto_secrets_are_encrypted_per_user(world):
    created = create(world.client, CRYPTO_CREATE, "user-a")

    blob = world.repository.list_accounts(user_id="user-a")[0]["credential_blob"]
    assert "synthetic-secret" not in blob
    vault = credential_manager.get_vault()
    assert json.loads(vault.manager_for("user-a").decrypt(blob)) == {
        "api_secret": "synthetic-secret"
    }
    assert world.repository.get_account(
        user_id="user-a", platform="crypto", account_id=created["id"]
    )["metadata"]["api_key"] == "public-key"
