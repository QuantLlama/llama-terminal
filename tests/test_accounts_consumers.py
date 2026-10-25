"""Every consumer of a tenant-scoped account registry, at its real seam.

The previous change moved broker accounts into PostgreSQL behind managers whose
storage methods require a keyword-only ``user_id``. Everything outside that edit
surface kept calling them without a tenant, so trading, symbol lists, positions,
the order gateway, the market-data engine, footprint and replication would have
raised ``TypeError`` in production while the suite stayed green.

This module pins the three cases apart:

* request paths resolve the tenant from the bearer token and pass it down, so an
  anonymous call is a 401 that touches nothing and a token only ever reaches that
  user's rows;
* background consumers use the active-tenant holder and skip while it is empty;
* the trading route inventory is asserted structurally, so a new call that drops
  ``user_id`` - or a literal ``default_user`` - fails the build.

Route assertions run through the real handlers extracted from the real sources,
the real managers, the real repository and a fake DB-API driver. Connector seams
(the crypto exchange client needs ``ccxt``, which the CI dependency set does not
install) are replaced with a recording stub so the tenant actually handed to them
is observable.
"""
import ast
import asyncio
import logging
import re
import sys
import types
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
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
from src.services import user_repository  # noqa: E402
from src.services import active_tenant  # noqa: E402
from src.services import crypto_manager as crypto_manager_module  # noqa: E402
from src.services import mt5_manager as mt5_manager_module  # noqa: E402
from src.services import ninjatrader_manager as nt8_manager_module  # noqa: E402
from src.services import tradovate_manager as tradovate_manager_module  # noqa: E402
from src.services.crypto_manager import get_crypto_manager  # noqa: E402
from src.services.mt5_manager import get_manager  # noqa: E402
from src.services.ninjatrader_manager import get_nt8_manager  # noqa: E402
from src.services.tradovate_manager import get_tradovate_manager  # noqa: E402
from src.services.user_repository import PostgresUserRepository  # noqa: E402
from test_database_postgres import FakePostgres, open_fake_connection  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/platform/api/main.py"
ACCOUNTS_API = ROOT / "src/platform/api/accounts_api.py"
FOOTPRINT_API = ROOT / "src/platform/api/footprint_api.py"
WEB = ROOT / "src/platform/web"

TOKENS = {"token-a": "user-a", "token-b": "user-b"}


# ── fake identity and fake database ────────────────────────────────


class FakeSupabaseUser:
    def __init__(self, user_id):
        self.user = SimpleNamespace(id=user_id, email=f"{user_id}@example.invalid")


class FakeSupabase:
    """Accepts exactly the synthetic tokens these tests issue."""

    def __init__(self, tokens):
        self.tokens = dict(tokens)
        self.auth = SimpleNamespace(get_user=self._get_user)

    def _get_user(self, token):
        if token not in self.tokens:
            raise RuntimeError("invalid token")
        return FakeSupabaseUser(self.tokens[token])


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
    monkeypatch.setenv(
        credential_manager.MASTER_KEY_ENV, "synthetic-installation-master-secret"
    )
    credential_manager.reset_vault()

    # Account files used to resolve under project-root paths that are not mounted
    # volumes; this unit must not create any of them.
    data_root = tmp_path / "data"
    monkeypatch.setattr(
        mt5_manager_module, "get_data_path", lambda *parts: str(data_root.joinpath(*parts))
    )
    for module in (
        mt5_manager_module,
        crypto_manager_module,
        nt8_manager_module,
        tradovate_manager_module,
    ):
        monkeypatch.setattr(module, "_manager", None)

    active_tenant.clear_active_user_id()
    try:
        yield World(
            client=None, store=store, repository=repository, data_root=data_root
        )
    finally:
        database_module.reset_repository()
        user_repository.reset_repository()
        credential_manager.reset_vault()
        active_tenant.clear_active_user_id()
        for module in (
            mt5_manager_module,
            crypto_manager_module,
            nt8_manager_module,
            tradovate_manager_module,
        ):
            module._manager = None


def add_crypto(world, user, name="bybit", api_key="public-key-a"):
    return get_crypto_manager().add_account(
        name=name,
        broker="bybit",
        api_key=api_key,
        api_secret="synthetic-api-secret",
        account_type="demo",
        user_id=user,
    )


def add_tradovate(world, user, name="tv-demo", username="tv-user"):
    return get_tradovate_manager().add_account(
        name=name,
        username=username,
        password="synthetic-password",
        app_id="Quantum",
        app_version="1.0.0",
        cid="12345",
        sec="synthetic-sec",
        environment="demo",
        user_id=user,
    )


# ── handler composition ────────────────────────────────────────────


def _module_body(path, function_names, class_names=()):
    source = path.read_text()
    tree = ast.parse(source)
    functions = {
        node.name: node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    missing = (set(function_names) - set(functions)) | (
        set(class_names) - set(classes)
    )
    assert missing == set(), f"{path.name} is missing {sorted(missing)}"
    nodes = [functions[name] for name in function_names] + [
        classes[name] for name in class_names
    ]
    # Source order: a decorator such as ``response_model=List[AccountResponse]``
    # runs before the body, so the model has to be defined first.
    return source, sorted(nodes, key=lambda node: node.lineno)


def _run(path, nodes, namespace):
    exec(
        compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"),
        namespace,
    )


def _crypto_connector_stub(monkeypatch, calls, positions):
    class Connector:
        def get_positions(self, symbol=None):
            return positions

    module = types.ModuleType("src.live.crypto_connector")
    module.get_connector = lambda account_id, *, user_id: (
        calls.append((account_id, user_id)) or Connector()
    )
    monkeypatch.setitem(sys.modules, "src.live.crypto_connector", module)
    return module


def positions_app():
    """The real /api/positions handler from main.py, crypto branch only."""
    source, nodes = _module_body(MAIN, ["get_positions"])
    app = FastAPI()
    _run(
        MAIN,
        nodes,
        {
            "app": app,
            "Query": Query,
            "Depends": Depends,
            "Optional": Optional,
            "List": List,
            "Dict": Dict,
            "Any": Any,
            "HTTPException": HTTPException,
            "logger": logging.getLogger("consumers-main"),
            "asyncio": asyncio,
            "get_authenticated_user_id": auth_module.get_authenticated_user_id,
            "resolve_symbol": lambda symbol: symbol,
            "sanitize_float": lambda value: value,
            "_connection_state": {"platform": "crypto"},
        },
    )
    return app


def footprint_app(recorder):
    """The real /api/footprint route, with its crypto worker recorded."""
    source, nodes = _module_body(FOOTPRINT_API, ["get_footprint"])
    app = FastAPI()
    router = APIRouter(prefix="/api/footprint", tags=["Footprint Chart"])

    async def fake_crypto_footprint(symbol, timeframe, limit, *, user_id):
        recorder.append({"user_id": user_id, "symbol": symbol})
        return [{"time": 1, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}]

    _run(
        FOOTPRINT_API,
        nodes,
        {
            "router": router,
            "Query": Query,
            "Depends": Depends,
            "Optional": Optional,
            "HTTPException": HTTPException,
            "logger": logging.getLogger("consumers-footprint"),
            "get_authenticated_user_id": auth_module.get_authenticated_user_id,
            "get_crypto_footprint": fake_crypto_footprint,
            "get_mt5_footprint": lambda *args, **kwargs: [],
            "_get_tick_size": lambda symbol: 0.25,
            "_get_digits": lambda symbol: 2,
        },
    )
    app.include_router(router)
    return app


def accounts_app(handler_names, calls=None):
    """Real accounts_api handlers with the real per-user managers."""
    source, nodes = _module_body(
        ACCOUNTS_API, list(handler_names), class_names=["AccountResponse"]
    )
    app = FastAPI()
    router = APIRouter(prefix="/api/accounts", tags=["Accounts"])

    def record(platform, factory):
        def getter():
            if calls is not None:
                calls.append(platform)
            return factory()
        return getter

    _run(
        ACCOUNTS_API,
        nodes,
        {
            "router": router,
            "Depends": Depends,
            "Query": Query,
            "Body": Any,
            "HTTPException": HTTPException,
            "BaseModel": BaseModel,
            "Optional": Optional,
            "List": List,
            "Dict": Dict,
            "Any": Any,
            "logger": logging.getLogger("consumers-accounts"),
            "os": __import__("os"),
            "asyncio": asyncio,
            "get_authenticated_user_id": auth_module.get_authenticated_user_id,
            "get_manager": record("mt5", get_manager),
            "get_crypto_manager": record("crypto", get_crypto_manager),
            "get_nt8_manager": record("nt8", get_nt8_manager),
            "get_tradovate_manager": record("tradovate", get_tradovate_manager),
            "get_connector": lambda account_id, **kwargs: None,
            "get_tradovate_connector": lambda account_id, **kwargs: None,
            "set_active_user_id": active_tenant.set_active_user_id,
            "DatabaseNotConfigured": user_repository.DatabaseNotConfigured,
        },
    )
    app.include_router(router)
    return app


def _client(app):
    return TestClient(app, raise_server_exceptions=False)


# ── request paths: authentication boundary ─────────────────────────


def test_trading_route_without_a_token_is_401_and_reads_no_account(
    world, monkeypatch
):
    connector_calls = []
    _crypto_connector_stub(monkeypatch, connector_calls, positions=[])
    app = positions_app()
    before = world.store.snapshot()

    response = _client(app).get("/api/positions")

    assert response.status_code == 401
    assert connector_calls == []
    assert world.store.snapshot() == before


def test_footprint_route_without_a_token_is_401_and_reads_no_account(world):
    recorder = []
    before = world.store.snapshot()

    response = _client(footprint_app(recorder)).get(
        "/api/footprint", params={"symbol": "BTC/USDT", "platform": "crypto"}
    )

    assert response.status_code == 401
    assert recorder == []
    assert world.store.snapshot() == before


def test_account_listing_without_a_token_is_401_and_reads_no_account(world):
    calls = []
    before = world.store.snapshot()

    response = _client(accounts_app(["get_accounts"], calls=calls)).get("/api/accounts")

    assert response.status_code == 401
    assert calls == []
    assert world.store.snapshot() == before


# ── request paths: a token sees exactly its own accounts ───────────


def test_trading_route_uses_the_token_tenant_and_nothing_else(world, monkeypatch):
    account = add_crypto(world, "user-b")
    connector_calls = []
    positions = [{"symbol": "BTC/USDT", "profit": 1.5}]
    _crypto_connector_stub(monkeypatch, connector_calls, positions=positions)
    client = _client(positions_app())

    response_a = client.get("/api/positions", headers=world.headers("user-a"))
    assert response_a.status_code == 200
    assert response_a.json() == []
    assert connector_calls == [], "user-a has no account, so nothing may be contacted"

    response_b = client.get("/api/positions", headers=world.headers("user-b"))
    assert response_b.status_code == 200
    assert response_b.json() == positions
    assert connector_calls == [(account["id"], "user-b")]


def test_footprint_route_passes_the_token_tenant_to_the_crypto_worker(world):
    recorder = []
    client = _client(footprint_app(recorder))

    response = client.get(
        "/api/footprint",
        params={"symbol": "BTC/USDT", "platform": "crypto"},
        headers=world.headers("user-b"),
    )

    assert response.status_code == 200
    assert recorder == [{"user_id": "user-b", "symbol": "BTC/USDT"}]


def test_tradovate_accounts_are_scoped_to_their_owner(world):
    created = add_tradovate(world, "user-b")
    client = _client(accounts_app(["get_accounts"]))

    listing_a = client.get("/api/accounts", headers=world.headers("user-a"))
    listing_b = client.get("/api/accounts", headers=world.headers("user-b"))

    assert listing_a.status_code == 200
    assert listing_a.json() == []
    assert [row["user_id"] for row in world.accounts()] == ["user-b"]
    assert [account["platform"] for account in listing_b.json()] == ["tradovate"]
    assert listing_b.json()[0]["id"] == created["id"]
    assert "password" not in listing_b.json()[0]
    assert "sec" not in listing_b.json()[0]
    # Reading it back is tenant scoped too.
    assert get_tradovate_manager().get_account(created["id"], user_id="user-a") is None
    assert (
        get_tradovate_manager().get_account(created["id"], user_id="user-b")["username"]
        == "tv-user"
    )


def test_every_platform_is_listed_from_the_repository(world):
    add_crypto(world, "user-b")
    add_tradovate(world, "user-b")
    get_nt8_manager().add_account(
        name="bridge", exchange_dir="/tmp/synthetic-exchange", user_id="user-b"
    )

    listing = _client(accounts_app(["get_accounts"])).get(
        "/api/accounts", headers=world.headers("user-b")
    )

    assert listing.status_code == 200, listing.text
    assert sorted(account["platform"] for account in listing.json()) == [
        "crypto",
        "nt8",
        "tradovate",
    ]


def test_selecting_a_master_account_activates_that_tenant(world):
    account = add_crypto(world, "user-b")
    client = _client(accounts_app(["get_accounts", "set_master_account", "_account_manager"]))

    response = client.post(
        f"/api/accounts/{account['id']}/master",
        params={"platform": "crypto"},
        headers=world.headers("user-b"),
    )

    assert response.status_code == 200, response.text
    assert active_tenant.get_active_user_id() == "user-b"


def test_tradovate_writes_no_file_under_src_config(world):
    config_dir = ROOT / "src" / "config"
    before = sorted(path.name for path in config_dir.iterdir())

    created = add_tradovate(world, "user-b")
    client = _client(
        accounts_app(
            ["get_accounts", "set_master_account", "remove_account", "_account_manager"]
        )
    )
    assert client.get("/api/accounts", headers=world.headers("user-b")).status_code == 200
    assert client.post(
        f"/api/accounts/{created['id']}/master",
        params={"platform": "tradovate"},
        headers=world.headers("user-b"),
    ).status_code == 200
    assert client.delete(
        f"/api/accounts/{created['id']}",
        params={"platform": "tradovate"},
        headers=world.headers("user-b"),
    ).status_code == 200

    assert sorted(path.name for path in config_dir.iterdir()) == before
    assert not (config_dir / "tradovate_accounts.json").exists()


# ── structural contract over every touched consumer ────────────────

TENANT_SCOPED_CALLS = {
    "get_accounts",
    "get_account",
    "get_account_full",
    "add_account",
    "update_account",
    "remove_account",
    "set_master_account",
    "test_connection",
    "start_instance",
    "stop_instance",
    "get_connector",
    "get_crypto_connector",
}

CONSUMER_MODULES = {
    "src/platform/api/main.py",
    "src/platform/api/accounts_api.py",
    "src/platform/api/footprint_api.py",
    "src/live/crypto_connector.py",
    "src/services/order_gateway/gateway.py",
    "src/services/market_data_engine/engine.py",
    "src/services/replication_service.py",
    "src/services/tradovate_manager.py",
}

REQUEST_PATH_MODULES = {
    "src/platform/api/main.py",
    "src/platform/api/accounts_api.py",
    "src/platform/api/footprint_api.py",
}

# Loops and engine internals: no request context, so they read the holder.
BACKGROUND_FUNCTIONS = {
    ("src/platform/api/main.py", "monitor_crypto_accounts"),
    ("src/services/order_gateway/gateway.py", "_get_connector"),
    ("src/services/market_data_engine/engine.py", "_get_connector"),
    ("src/services/market_data_engine/engine.py", "_poll_crypto_symbol"),
    ("src/services/replication_service.py", "replicate_to_nt8_sync"),
}


def _trees():
    for name in sorted(CONSUMER_MODULES):
        path = ROOT / name
        yield name, path.read_text(), ast.parse(path.read_text())


def _callee_name(call):
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _tenant_calls(node):
    return [
        call for call in ast.walk(node)
        if isinstance(call, ast.Call) and _callee_name(call) in TENANT_SCOPED_CALLS
    ]


def _function_defs(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _calls_name(node, name):
    return any(
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == name
        for call in ast.walk(node)
    )


def _user_id_parameter(node):
    args = node.args
    for argument in (
        list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
    ):
        if argument.arg == "user_id":
            return argument
    return None


def _user_id_default(node):
    """Return the default expression of a ``user_id`` parameter, if any."""
    positional = list(node.args.posonlyargs) + list(node.args.args)
    default_by_name = {}
    if node.args.defaults:
        for argument, default in zip(positional[-len(node.args.defaults):], node.args.defaults):
            default_by_name[argument.arg] = default
    for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        if default is not None:
            default_by_name[argument.arg] = default
    return default_by_name.get("user_id")


def _is_route(node):
    """A decorated handler is reachable over HTTP; a bare def is a helper."""
    return bool(node.decorator_list)


def _declares_authenticated_user_id(node):
    """True when ``user_id`` is required from the bearer-token dependency."""
    default = _user_id_default(node)
    if default is None:
        return False
    if not isinstance(default, ast.Call):
        return False
    if not isinstance(default.func, ast.Name) or default.func.id != "Depends":
        return False
    if not default.args or not isinstance(default.args[0], ast.Name):
        return False
    return default.args[0].id == "get_authenticated_user_id"


def test_every_tenant_scoped_call_passes_a_resolved_user_id():
    offenders = []
    for module, _, tree in _trees():
        for call in _tenant_calls(tree):
            keyword = next(
                (item for item in call.keywords if item.arg == "user_id"), None
            )
            if keyword is None:
                offenders.append(f"{module}:{call.lineno} {_callee_name(call)}()")
            elif not isinstance(keyword.value, ast.Name):
                offenders.append(
                    f"{module}:{call.lineno} {_callee_name(call)}(user_id=<not a bound id>)"
                )
    assert offenders == [], (
        "every account call must pass a resolved tenant: " + "; ".join(offenders)
    )


def test_no_module_reintroduces_a_shared_tenant_literal():
    offenders = [
        module for module, source, _ in _trees() if "default_user" in source
    ]
    assert offenders == [], "no consumer may fall back to a shared tenant: " + str(
        offenders
    )


def test_every_function_touching_accounts_takes_a_required_tenant():
    offenders = []
    for module, _, tree in _trees():
        for node in _function_defs(tree):
            if not _tenant_calls(node):
                continue
            if _calls_name(node, "get_active_user_id"):
                # Background consumer: pinned by the guard test below.
                continue
            if _user_id_parameter(node) is None:
                offenders.append(f"{module}:{node.lineno} {node.name} takes no user_id")
                continue
            default = _user_id_default(node)
            if default is not None and not _declares_authenticated_user_id(node):
                offenders.append(
                    f"{module}:{node.lineno} {node.name} has an optional tenant"
                )
    assert offenders == [], (
        "every account call needs a mandatory tenant: " + "; ".join(offenders)
    )


def test_the_migrated_registry_never_defaults_its_tenant():
    path = ROOT / "src/services/tradovate_manager.py"
    offenders = [
        f"line {node.lineno} {node.name}"
        for node in _function_defs(ast.parse(path.read_text()))
        if _user_id_parameter(node) is not None and _user_id_default(node) is not None
    ]
    assert offenders == [], sorted(offenders)


def test_request_paths_take_the_tenant_from_the_token_only():
    offenders = []
    for module, _, tree in _trees():
        if module not in REQUEST_PATH_MODULES:
            continue
        for node in _function_defs(tree):
            if not _tenant_calls(node):
                continue
            if (module, node.name) in BACKGROUND_FUNCTIONS:
                continue
            if _calls_name(node, "get_active_user_id"):
                offenders.append(
                    f"{module}:{node.lineno} {node.name} reads the ambient tenant"
                )
                continue
            if _is_route(node):
                if not _declares_authenticated_user_id(node):
                    offenders.append(
                        f"{module}:{node.lineno} {node.name} is not token authenticated"
                    )
            elif _user_id_parameter(node) is None:
                offenders.append(
                    f"{module}:{node.lineno} {node.name} takes no user_id"
                )
    assert offenders == [], (
        "request paths must resolve the tenant from the token: " + "; ".join(offenders)
    )


def test_background_consumers_guard_on_the_active_tenant():
    offenders = []
    for module, _, tree in _trees():
        for node in _function_defs(tree):
            if (module, node.name) not in BACKGROUND_FUNCTIONS:
                continue
            calls = _tenant_calls(node)
            if not _calls_name(node, "get_active_user_id"):
                offenders.append(f"{module}:{node.name} never reads the holder")
                continue
            if not _calls_name(node, "note_missing_active_user"):
                offenders.append(f"{module}:{node.name} never logs the skip")
                continue
            guards = [
                statement
                for statement in ast.walk(node)
                if isinstance(statement, ast.If)
                and isinstance(statement.test, ast.UnaryOp)
                and isinstance(statement.test.op, ast.Not)
                and isinstance(statement.test.operand, ast.Name)
                and statement.test.operand.id == "user_id"
                and any(
                    isinstance(
                        inner, ast.Call
                    ) and isinstance(inner.func, ast.Name)
                    and inner.func.id == "note_missing_active_user"
                    for inner in ast.walk(statement)
                )
            ]
            if not guards:
                offenders.append(f"{module}:{node.name} has no skip guard")
                continue
            earliest_guard = min(guard.lineno for guard in guards)
            for call in calls:
                if call.lineno < earliest_guard:
                    offenders.append(
                        f"{module}:{node.name} touches an account before the guard"
                    )
                    break
    assert offenders == [], (
        "background consumers must skip while no tenant is active: "
        + "; ".join(offenders)
    )


def test_background_consumers_are_the_only_ambient_tenant_readers():
    readers = {
        (module, node.name)
        for module, _, tree in _trees()
        for node in _function_defs(tree)
        if _calls_name(node, "get_active_user_id")
    }
    assert readers - BACKGROUND_FUNCTIONS == set(), sorted(
        readers - BACKGROUND_FUNCTIONS
    )


# ── the browser call sites ─────────────────────────────────────────

ACCOUNTS_WEB_FILES = {
    "index.html": WEB / "index.html",
    "SettingsModal.js": WEB / "components/SettingsModal.js",
    "OrderEntry_Professional.js": WEB / "components/OrderEntry_Professional.js",
}

CALL_SITE_RE = re.compile(
    r"(?<![A-Za-z0-9_$.])(window\.authFetch|authFetch|fetch)\s*\(\s*(['\"`])([^'\"`]*)\2"
)
BARE_FETCH_URL_RE = re.compile(r"(?<![A-Za-z0-9_$.])fetch\s*\(\s*url\b")


def test_every_accounts_call_site_uses_the_shared_auth_helper():
    found = []
    for name, path in ACCOUNTS_WEB_FILES.items():
        source = path.read_text(encoding="utf-8")
        for match in CALL_SITE_RE.finditer(source):
            callee, endpoint = match.group(1), match.group(3)
            if endpoint.startswith("/api/accounts"):
                found.append((name, endpoint, callee))

    assert found, "sanity: these pages call the accounts API"
    bare = [(name, endpoint) for name, endpoint, callee in found if callee != "window.authFetch"]
    assert bare == [], f"/api/accounts requires a bearer token: {bare}"
    assert len(found) == 10, found


def test_no_accounts_call_site_fetches_a_computed_url_without_the_helper():
    offenders = []
    for name, path in ACCOUNTS_WEB_FILES.items():
        source = path.read_text(encoding="utf-8")
        if BARE_FETCH_URL_RE.search(source):
            offenders.append(name)
    assert offenders == [], (
        "the PATCH/POST accounts call builds its URL first and must still use "
        "window.authFetch: " + ", ".join(offenders)
    )
    settings = (WEB / "components/SettingsModal.js").read_text(encoding="utf-8")
    assert "window.authFetch(url" in settings


# The trading routes this change made token-authenticated. Their page call sites
# have to carry the bearer header too, or the chart, the account panel and order
# entry answer 401 on a logged-in session.
TRADING_ENDPOINTS = (
    "/api/symbols",
    "/api/symbol_info",
    "/api/timeframes",
    "/api/deals",
    "/api/account",
    "/api/order",
    "/api/modify",
    "/api/realtime",
    "/api/positions",
    "/api/history",
)


def _trading_call_sites(source, callee):
    return [
        match.group(3)
        for match in CALL_SITE_RE.finditer(source)
        if match.group(1) == callee
        and not match.group(3).startswith("/api/accounts")
        and match.group(3).startswith(TRADING_ENDPOINTS)
    ]


def test_index_page_sends_the_token_to_the_trading_routes():
    source = (WEB / "index.html").read_text(encoding="utf-8")
    bare = _trading_call_sites(source, "fetch")
    assert bare == [], f"token-authenticated routes must use window.authFetch: {bare}"

    authenticated = Counter(_trading_call_sites(source, "window.authFetch"))
    assert authenticated == Counter({
        "/api/symbols?platform=${platform}": 1,
        "/api/symbol_info?symbol=${encodeURIComponent(activeSymbol)}": 1,
        "/api/timeframes?platform=${platform}": 1,
        "/api/deals?platform=${platformParam}&days=9999": 1,
        "/api/account?platform=${platformParam}": 1,
        "/api/order": 1,
        "/api/realtime_batch?symbols=${encodeURIComponent(mappedSymbols)}&platform=${platformType}": 1,
    }), authenticated
