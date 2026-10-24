"""Public runtime config tests: synthetic values only, no platform startup."""

import base64
import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
URL = "https://auth.example.invalid"
ERROR_SCRIPT = 'window.PUBLIC_AUTH_CONFIG = null;\nthrow new Error("Public authentication configuration unavailable; configure SUPABASE_URL and an anon SUPABASE_ANON_KEY.");\n'


def token(payload=None, header=None):
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")

    return ".".join((encode(header or {"alg": "HS256", "typ": "JWT"}),
                     encode(payload if payload is not None else {"role": "anon"}),
                     encode("synthetic-signature")))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", URL)
    monkeypatch.setenv("SUPABASE_ANON_KEY", token())
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "private-admin-sentinel")
    from src.platform.api.public_auth_config import router

    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        yield client


def assert_headers(response):
    assert response.headers["content-type"].startswith("application/javascript")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_anon_runtime_config_exposes_only_public_fields(client):
    response = client.get("/api/public-auth-config.js")
    assert response.status_code == 200
    assert_headers(response)
    config = json.loads(response.text.removeprefix("window.PUBLIC_AUTH_CONFIG = ").removesuffix(";\n"))
    assert config == {"SUPABASE_URL": URL, "SUPABASE_ANON_KEY": token()}
    assert "private-admin-sentinel" not in response.text


@pytest.mark.parametrize("key", [
    None, "", "malformed-private-sentinel", "sb_secret_private-sentinel",
    token({"role": "service_role"}), token({"role": "admin"}),
    token({"role": "authenticated"}), token({}), token([]),
    token(header={"alg": "none"}), "a.b.c", token() + ".extra",
    token().rsplit(".", 1)[0] + ".", "!!!." + token().split(".")[1] + ".abc",
])
def test_invalid_key_fails_closed_without_echo(client, monkeypatch, key):
    if key is None:
        monkeypatch.delenv("SUPABASE_ANON_KEY")
    else:
        monkeypatch.setenv("SUPABASE_ANON_KEY", key)
    response = client.get("/api/public-auth-config.js")
    assert response.status_code == 503
    assert_headers(response)
    assert response.text == ERROR_SCRIPT
    assert URL not in response.text
    if key:
        assert key not in response.text
    assert "private-admin-sentinel" not in response.text
    assert client.get("/api/public-auth-config.js").text == ERROR_SCRIPT


@pytest.mark.parametrize("url", [None, "", "not-a-url", "javascript:alert(1)",
                                 "https://user:private@auth.example.invalid", "https://",
                                 "https://auth.example.invalid?private=value"])
def test_missing_or_malformed_url_fails_closed(client, monkeypatch, url):
    if url is None:
        monkeypatch.delenv("SUPABASE_URL")
    else:
        monkeypatch.setenv("SUPABASE_URL", url)
    response = client.get("/api/public-auth-config.js")
    assert response.status_code == 503
    assert_headers(response)
    assert response.text == ERROR_SCRIPT
    assert token() not in response.text


def test_config_is_read_at_request_time(client, monkeypatch):
    assert client.get("/api/public-auth-config.js").status_code == 200
    monkeypatch.setenv("SUPABASE_ANON_KEY", token({"role": "service_role"}))
    assert client.get("/api/public-auth-config.js").status_code == 503
    monkeypatch.setenv("SUPABASE_ANON_KEY", token())
    assert client.get("/api/public-auth-config.js").status_code == 200


def test_javascript_embedding_escapes_html_and_line_separators(client, monkeypatch):
    url = URL + "/</script><script>alert('x')&\u2028\u2029"
    monkeypatch.setenv("SUPABASE_URL", url)
    response = client.get("/api/public-auth-config.js")
    assert response.status_code == 200
    assert "<" not in response.text and ">" not in response.text and "&" not in response.text
    assert "\u2028" not in response.text and "\u2029" not in response.text
    config = json.loads(response.text.removeprefix("window.PUBLIC_AUTH_CONFIG = ").removesuffix(";\n"))
    assert config["SUPABASE_URL"] == url


def test_frontend_loads_runtime_config_before_babel_without_embedded_values():
    html = (ROOT / "src/platform/web/index.html").read_text()
    script = '<script src="/api/public-auth-config.js"></script>'
    assert script in html
    assert html.index(script) < html.index('<script type="text/babel">')
    assert "const { SUPABASE_URL, SUPABASE_ANON_KEY } = window.PUBLIC_AUTH_CONFIG;" in html
    assert not re.search(r"const SUPABASE_(?:URL|ANON_KEY)\s*=\s*['\"]", html)
    assert not re.search(r"https://[a-z0-9]+\.supabase\.co|eyJ[A-Za-z0-9_-]+\.", html)


def test_popout_session_semantics_preserved():
    html = (ROOT / "src/platform/web/index.html").read_text()
    assert 'new URLSearchParams(window.location.search).get("popout") === "true"' in html
    for option in ("persistSession", "autoRefreshToken", "detectSessionInUrl"):
        assert f"{option}: !isPopoutMode" in html
    assert "supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {" in html


def test_router_registered_before_spa_fallback():
    source = (ROOT / "src/platform/api/main.py").read_text()
    assert source.index("app.include_router(public_auth_config_router)") < source.index('@app.get("/{path:path}")')
