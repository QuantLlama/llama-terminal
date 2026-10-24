"""Exercise real router composition without broker-backed application startup."""
import ast
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[1]
ROUTER_MODULES = {
    "src.platform.api.runtime_api",
    "src.platform.api.version_api",
}


def composed_client(health_provider):
    """Execute the actual isolated imports/includes and SPA in source order."""
    source = ROOT / "src/platform/api/main.py"
    tree = ast.parse(source.read_text())
    nodes = []
    includes = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module in ROUTER_MODULES:
            nodes.append(node)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if (isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "app"
                    and call.func.attr == "include_router"
                    and call.args
                    and ((isinstance(call.args[0], ast.Name)
                          and call.args[0].id == "version_router")
                         or (isinstance(call.args[0], ast.Call)
                             and isinstance(call.args[0].func, ast.Name)
                             and call.args[0].func.id == "create_runtime_router"))):
                nodes.append(node)
                includes.append(node)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "serve_static":
            nodes.append(node)
    assert len(includes) == 2, "Health and version must be composed as public routers"
    app = FastAPI()
    with TemporaryDirectory(prefix="route-composition-") as web_dir:
        Path(web_dir, "index.html").write_text("isolated SPA fallback")
        namespace = dict(app=app, get_platform_health=health_provider,
                         FileResponse=FileResponse, os=os, WEB_DIR=web_dir)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)
        with TestClient(app) as client:
            yield client


@pytest.fixture
def route_client():
    from contextlib import contextmanager
    return contextmanager(composed_client)


def test_public_route_inventory_and_real_include_order(route_client):
    with route_client(lambda: {"ready_for_ui": True}) as client:
        paths = client.get("/openapi.json").json()["paths"]
        assert [(path, set(methods)) for path, methods in paths.items()] == [
            ("/health", {"get"}), ("/api/health", {"get"}),
            ("/api/platform/version", {"get"}), ("/{path}", {"get"}),
        ]
        assert client.get("/unmatched-ui-page").text == "isolated SPA fallback"


def test_health_provider_is_live_and_shared_without_copied_state(route_client):
    payload = {"ready_for_ui": False, "services": {}, "timestamp": 1.0}
    calls = []

    def provider():
        calls.append(True)
        return payload

    with route_client(provider) as client:
        assert calls == []
        assert client.get("/api/health").status_code == 503
        payload["ready_for_ui"] = True
        assert client.get("/api/health").json() == payload
        assert client.get("/api/health").status_code == 200
        assert client.get("/health").json() == payload
        assert len(calls) == 4
