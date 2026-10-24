"""Transport hardening for the public origin.

Without HSTS a browser may still attempt a plain-HTTP request and briefly show
the page as not secure, even though the certificate chain is valid.
"""
import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def _middleware_namespace():
    source = ROOT / "src/platform/api/main.py"
    text = source.read_text()
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "security_headers":
            app = FastAPI()
            ns = {"app": app, "Request": __import__("fastapi").Request}
            exec(compile(ast.parse(ast.get_source_segment(text, node)), str(source), "exec"), ns)
            app.middleware("http")(ns["security_headers"])
            from fastapi.responses import JSONResponse

            @app.get("/probe")
            async def probe():
                return JSONResponse({"ok": True})

            return TestClient(app)
    raise AssertionError("security_headers middleware is missing")


def test_responses_advertise_hsts_and_deny_sniffing():
    with _middleware_namespace() as client:
        response = client.get("/probe")
    assert response.status_code == 200
    assert response.headers["strict-transport-security"] == "max-age=31536000"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_body_and_status_are_unchanged():
    with _middleware_namespace() as client:
        response = client.get("/probe")
    assert response.json() == {"ok": True}
