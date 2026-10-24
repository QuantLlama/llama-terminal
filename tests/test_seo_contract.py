"""Technical SEO contract: crawler files, SPA head metadata and route order.

The FastAPI surface is composed in isolation from the real ``seo_api`` router plus the real
SPA catch-all taken out of ``src/platform/api/main.py``. The broker-backed application is
never imported and no real configuration or credential is read.
"""
import ast
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

import pytest
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/platform/api/main.py"
INDEX_HTML = ROOT / "src/platform/web/index.html"
SITEMAP_NAMESPACE = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
SPA_FALLBACK = '<!doctype html>\n<html lang="es"><body>isolated SPA sentinel</body></html>'

# Surfaces that exist only for the API/runtime and are never needed to render the SPA.
ALLOWED_DISALLOW = {"/api/", "/live_status.json", "/debug/"}
# Asset trees the SPA needs while rendering; blocking them would break crawling of the page.
RENDER_REQUIRED_PREFIXES = ("/", "/components/", "/lib/", "/images/", "/src/live/")

ATTRIBUTE_RE = re.compile(r'([a-zA-Z][-\w:]*)\s*=\s*"([^"]*)"')
META_TAG_RE = re.compile(r"<meta\b[^>]*>")
LINK_TAG_RE = re.compile(r"<link\b[^>]*>")
JSON_LD_RE = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)


def _main_composition_nodes():
    """Collect the real seo import, its include call and the SPA catch-all in source order."""
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    nodes = []
    includes = []
    spa = None
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "src.platform.api.seo_api":
            nodes.append(node)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if (isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "app"
                    and call.func.attr == "include_router"
                    and call.args
                    and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == "seo_router"):
                nodes.append(node)
                includes.append(node)
        elif isinstance(node, ast.AsyncFunctionDef) and node.name == "serve_static":
            nodes.append(node)
            spa = node
    return nodes, includes, spa


@pytest.fixture
def seo_app(tmp_path):
    """Real seo router plus the real catch-all, registered in main.py source order."""
    nodes, includes, spa = _main_composition_nodes()
    assert len(includes) == 1, "main.py must include the seo router exactly once"
    assert spa is not None, "main.py must keep the SPA catch-all"
    assert includes[0].lineno < spa.lineno, "the seo router must be included before the catch-all"

    web_dir = tmp_path / "web"
    web_dir.mkdir()
    (web_dir / "index.html").write_text(SPA_FALLBACK, encoding="utf-8")

    app = FastAPI()
    namespace = dict(app=app, FileResponse=FileResponse, os=os, WEB_DIR=str(web_dir))
    module = ast.Module(body=list(nodes), type_ignores=[])
    exec(compile(module, str(MAIN), "exec"), namespace)
    return app


@pytest.fixture
def client(seo_app):
    with TestClient(seo_app) as test_client:
        yield test_client


def _route_paths(app):
    """Effective route paths in registration order, expanding included routers."""
    paths = []
    for route in app.routes:
        path = getattr(route, "path", None)
        if path is not None:
            paths.append(path)
            continue
        included = getattr(route, "original_router", None)
        if included is None:
            continue
        prefix = getattr(getattr(route, "include_context", None), "prefix", "") or ""
        paths.extend(f"{prefix}{getattr(inner, 'path', '')}" for inner in included.routes)
    return paths


def _robots_lines(client):
    return [line.strip() for line in client.get("/robots.txt").text.splitlines() if line.strip()]


def _sitemap_locs(client):
    root = ElementTree.fromstring(client.get("/sitemap.xml").content)
    return root, [element.text.strip() for element in root.iter(f"{SITEMAP_NAMESPACE}loc")]


def _head_html():
    html = INDEX_HTML.read_text(encoding="utf-8")
    return html, html[html.index("<head>") + len("<head>"):html.index("</head>")]


def _tag_attributes(markup, tag):
    return [dict(ATTRIBUTE_RE.findall(tag_text))
            for tag_text in re.findall(rf"<{tag}\b[^>]*>", markup)]


def _meta(head, name):
    return [tag["content"] for tag in _tag_attributes(head, "meta")
            if tag.get("name") == name and "content" in tag]


def _og(head, prop):
    return [tag["content"] for tag in _tag_attributes(head, "meta")
            if tag.get("property") == prop and "content" in tag]


# --- robots.txt -----------------------------------------------------------------------------

def test_robots_txt_serves_a_crawl_policy_as_plain_text(client):
    response = client.get("/robots.txt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "<html" not in response.text.lower()
    lines = _robots_lines(client)
    assert "User-agent: *" in lines
    assert "Allow: /" in lines
    assert "Disallow: /api/" in lines


def test_robots_txt_blocks_only_the_non_rendering_api_surface(client):
    disallowed = [line.split(":", 1)[1].strip() for line in _robots_lines(client)
                  if line.lower().startswith("disallow:")]

    assert "/live_status.json" in disallowed
    assert set(disallowed) <= ALLOWED_DISALLOW
    for prefix in RENDER_REQUIRED_PREFIXES:
        assert prefix not in disallowed, f"{prefix} is required for rendering"


def test_robots_txt_declares_the_sitemap_on_the_request_origin(client):
    sitemaps = [line.split(":", 1)[1].strip() for line in _robots_lines(client)
                if line.lower().startswith("sitemap:")]

    assert len(sitemaps) == 1
    parsed = urlparse(sitemaps[0])
    assert parsed.scheme in {"http", "https"}
    assert parsed.netloc
    assert parsed.path == "/sitemap.xml"
    assert parsed.netloc == urlparse(str(client.base_url)).netloc


# --- sitemap.xml ----------------------------------------------------------------------------

def test_sitemap_xml_is_valid_and_absolute(client):
    response = client.get("/sitemap.xml")

    assert response.status_code == 200
    assert "xml" in response.headers["content-type"]
    assert "<html" not in response.text.lower()
    root, locs = _sitemap_locs(client)
    assert root.tag == f"{SITEMAP_NAMESPACE}urlset"
    assert locs
    for loc in locs:
        parsed = urlparse(loc)
        assert parsed.scheme in {"http", "https"}, loc
        assert parsed.netloc, loc


def test_sitemap_xml_lists_only_routes_that_really_render(client):
    _, locs = _sitemap_locs(client)

    assert f"{str(client.base_url).rstrip('/')}/" in locs
    for loc in locs:
        path = urlparse(loc).path or "/"
        response = client.get(path)
        assert response.status_code == 200, loc
        assert SPA_FALLBACK in response.text, loc


# --- composition order ----------------------------------------------------------------------

def test_crawler_routes_are_registered_before_the_spa_catch_all(seo_app):
    paths = _route_paths(seo_app)
    spa_index = next(index for index, path in enumerate(paths)
                     if isinstance(path, str) and path.startswith("/{path"))

    assert "/robots.txt" in paths
    assert "/sitemap.xml" in paths
    assert paths.index("/robots.txt") < spa_index
    assert paths.index("/sitemap.xml") < spa_index


def test_crawler_routes_are_not_shadowed_by_the_spa_fallback(client):
    assert "isolated SPA sentinel" not in client.get("/robots.txt").text
    assert "isolated SPA sentinel" not in client.get("/sitemap.xml").text
    assert client.get("/unmatched-ui-page").text == SPA_FALLBACK
    assert client.get("/").text == SPA_FALLBACK


# --- SPA head metadata ----------------------------------------------------------------------

def test_head_declares_a_single_title_and_description():
    _, head = _head_html()

    titles = re.findall(r"<title>(.*?)</title>", head, re.S)
    assert len(titles) == 1
    assert "Quantum Llama" in titles[0]
    descriptions = _meta(head, "description")
    assert len(descriptions) == 1
    assert 50 <= len(descriptions[0]) <= 160, len(descriptions[0])


def test_head_declares_indexability_and_an_origin_relative_canonical():
    html, head = _head_html()

    assert '<html lang="es">' in html
    assert _meta(head, "robots") == ["index, follow"]
    canonicals = [tag.get("href") for tag in _tag_attributes(head, "link")
                  if tag.get("rel") == "canonical"]
    assert len(canonicals) == 1
    assert canonicals[0] == "/"
    assert urlparse(canonicals[0]).netloc == "", "no invented domain in the canonical"


def test_head_declares_open_graph_and_twitter_card():
    _, head = _head_html()

    assert _og(head, "og:type") == ["website"]
    for prop in ("og:site_name", "og:title", "og:description", "og:url", "og:image"):
        values = _og(head, prop)
        assert len(values) == 1 and values[0].strip(), prop
    assert _og(head, "og:url") == ["/"]
    assert _meta(head, "twitter:card") == ["summary_large_image"]
    for name in ("twitter:title", "twitter:description", "twitter:image"):
        values = _meta(head, name)
        assert len(values) == 1 and values[0].strip(), name


def test_head_declares_the_theme_color_of_the_dark_shell():
    _, head = _head_html()

    colors = _meta(head, "theme-color")
    assert len(colors) == 1
    assert re.fullmatch(r"#[0-9a-fA-F]{6}", colors[0])


def test_head_structured_data_is_a_truthful_software_application():
    _, head = _head_html()

    blocks = JSON_LD_RE.findall(head)
    assert len(blocks) == 1
    payload = json.loads(blocks[0])
    assert payload["@context"] == "https://schema.org"
    assert payload["@type"] == "SoftwareApplication"
    assert payload["name"].strip()
    assert payload["applicationCategory"].strip()
    assert payload["operatingSystem"].strip()
    assert payload["description"].strip()
    serialized = json.dumps(payload)
    for fabricated in ('"aggregateRating"', '"ratingValue"', '"reviewCount"',
                       '"review"', '"offers"', '"price"'):
        assert fabricated not in serialized


# --- preservation ---------------------------------------------------------------------------

def test_head_preserves_the_legacy_purge_script_and_runtime_mounts():
    html, head = _head_html()

    purge_order = [
        'localStorage.getItem("last_charts")',
        'localStorage.removeItem("last_charts")',
        'localStorage.removeItem("last_symbol")',
        'localStorage.removeItem("mt5_positions")',
    ]
    positions = [html.index(snippet) for snippet in purge_order]
    assert positions == sorted(positions)
    assert html.index(purge_order[0]) < html.index("</head>")
    assert "background-color: #050505 !important;" in head
    assert "#platform-loader {" in head
    assert '<div id="root"></div>' in html
    assert 'id="platform-loader"' in html
    for asset in ("/lib/react.production.min.js", "/lib/react-dom.production.min.js",
                  "/lib/supabase-js.js"):
        assert asset in html
