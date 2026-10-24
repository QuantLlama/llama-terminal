"""Crawler-facing endpoints: ``/robots.txt`` and ``/sitemap.xml``.

Both routes are registered in ``main.py`` *before* the SPA catch-all
(``@app.get("/{path:path}")``); otherwise the catch-all would answer them with
``index.html``. The module stays free of broker, database and credential state so
it can be composed and tested in isolation.

Public origin policy
--------------------
There is no fixed origin in configuration, so the public origin is derived from
the incoming request in one place only (:func:`public_origin`). This keeps every
environment (localhost, VPS, preview) truthful instead of baking in a domain.
A fixed canonical origin should be enforced by the reverse proxy/CDN; see
``docs/SEO.md``.
"""
from fastapi import APIRouter, Request
from fastapi.responses import Response

router = APIRouter()

# Routes that exist only for the API/runtime and are never needed to render the SPA.
DISALLOWED_PREFIXES = ("/api/",)
DISALLOWED_PATHS = ("/live_status.json", "/debug/")

# Public routes that really render the SPA shell. A sitemap must never advertise a
# URL that does not answer 200, so keep this list to routes proven to exist.
PUBLIC_PATHS = ("/",)


def public_origin(request: Request) -> str:
    """Return the origin of the incoming request without a trailing slash.

    Single place where the public origin is derived, shared by robots.txt and
    sitemap.xml. Never hardcode a production domain here.
    """
    return str(request.base_url).rstrip("/")


def absolute_url(request: Request, path: str) -> str:
    """Build an absolute URL for one public path on the current origin."""
    return f"{public_origin(request)}{path}"


def render_robots_txt(request: Request) -> str:
    lines = ["User-agent: *", "Allow: /", ""]
    lines.extend(f"Disallow: {path}" for path in DISALLOWED_PREFIXES + DISALLOWED_PATHS)
    lines.extend(["", f"Sitemap: {absolute_url(request, '/sitemap.xml')}", ""])
    return "\n".join(lines)


def render_sitemap_xml(request: Request) -> str:
    urls = "".join(
        f"  <url><loc>{absolute_url(request, path)}</loc></url>\n" for path in PUBLIC_PATHS
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}"
        "</urlset>\n"
    )


@router.get("/robots.txt", include_in_schema=False)
async def robots_txt(request: Request) -> Response:
    return Response(
        content=render_robots_txt(request),
        media_type="text/plain; charset=utf-8",
    )


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml(request: Request) -> Response:
    return Response(
        content=render_sitemap_xml(request),
        media_type="application/xml; charset=utf-8",
    )
