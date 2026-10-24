# Technical SEO

This document describes the crawler-facing surface of the served SPA and the honest limits
of what it can achieve. It covers technical SEO only; it does not change product content.

## What the application publishes

| URL | Source | Content type | Crawlable |
|-----|--------|--------------|-----------|
| `/robots.txt` | `src/platform/api/seo_api.py` | `text/plain; charset=utf-8` | yes |
| `/sitemap.xml` | `src/platform/api/seo_api.py` | `application/xml; charset=utf-8` | yes |
| `/` | `src/platform/web/index.html` via the SPA catch-all | `text/html` | yes |

Both crawler routes are included in `src/platform/api/main.py` **before** the SPA catch-all
`@app.get("/{path:path}")`. If the order is inverted, the catch-all answers `/robots.txt` and
`/sitemap.xml` with `index.html` and crawlers receive HTML instead of a crawl policy.
`tests/test_seo_contract.py` pins that order against the real router composition.

## Public origin

There is no fixed public origin in configuration. The origin is derived from the incoming
request in one place — `seo_api.public_origin()` — so every environment answers with its own
real host and no domain is invented in code.

The documented live deployment is `https://llama.nbmsystemas.com` (see `docs/CLOUD.md`). As a
consequence:

- `robots.txt` advertises `Sitemap: <request origin>/sitemap.xml`.
- `sitemap.xml` lists absolute URLs on the request origin.
- `index.html` keeps `canonical`, `og:url` and `og:image` origin-relative, so they resolve
  against whatever host serves the page.

A fixed canonical origin (including `Host` normalisation and a single 301 target) belongs at the
reverse proxy/CDN, not in this repository. Until it is enforced there, the canonical is
origin-relative rather than an absolute production URL.

## What is indexable

Only the SPA shell at `/`. Its `<head>` carries:

- one `<title>` and one `<meta name="description">` (50–160 characters),
- `<meta name="robots" content="index, follow">`,
- `<link rel="canonical" href="/">`,
- Open Graph (`og:type`, `og:site_name`, `og:title`, `og:description`, `og:url`, `og:image`),
- a `summary_large_image` Twitter card,
- `<meta name="theme-color" content="#050505">` matching the dark shell,
- one JSON-LD `SoftwareApplication` block describing the product as a web trading terminal.

The structured data is deliberately minimal: name, application category, operating system,
language, description and URL. It claims **no** `aggregateRating`, `review`, `offers` or price —
those values do not exist and fabricating them is a Search policy violation, not an optimisation.

## What is deliberately excluded and why

`robots.txt` disallows everything that is not needed to render the page:

| Path | Why |
|------|-----|
| `/api/` | JSON API for the SPA and other clients; not a document, nothing to index |
| `/live_status.json` | Runtime status payload polled by the UI; volatile machine data |
| `/debug/` | Operator diagnostics (`/debug/mt5`), never a public document |

The authenticated trading surface (workspaces, positions, charts, backtests) is served by the
same SPA behind Supabase login. It is excluded by access control rather than by `robots.txt`:
a crawler without a session only ever sees the app shell. Asset trees that the shell needs while
rendering (`/components/`, `/lib/`, `/images/`, `/src/live/`) stay crawlable on purpose —
blocking render resources breaks indexing of the page itself.

## How to verify

```bash
# Crawl policy: 200, text/plain, no HTML, absolute Sitemap line
curl -sS -D - -o /tmp/robots.txt https://<host>/robots.txt
grep -E '^(User-agent|Allow|Disallow|Sitemap):' /tmp/robots.txt

# Sitemap: 200, XML, every <loc> parses and every listed URL answers 200
curl -sS -D - -o /tmp/sitemap.xml https://<host>/sitemap.xml
python3 -c "import xml.etree.ElementTree as E; print([e.text for e in E.parse('/tmp/sitemap.xml').iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')])"

# Head metadata actually served
curl -sS https://<host>/ | sed -n '/<head>/,/<\/head>/p'

# Catch-all still serves the SPA shell for unmatched paths
curl -sS -o /dev/null -w '%{http_code} %{content_type}\n' https://<host>/unmatched-ui-page
```

Then, outside the repository: Google Search Console (submit `sitemap.xml`, inspect the URL),
Rich Results Test / Schema.org validator for the JSON-LD block, and a Lighthouse SEO audit.

Local regression guard (no network, no browser):

```bash
PYTHONDONTWRITEBYTECODE=1 venv_linux/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_seo_contract.py tests/test_api_route_composition.py
```

## Honest limits

- A login-gated analytics terminal does not rank on trading content it never publishes. Search
  visibility comes from public content — explanations, documentation, market commentary — which
  this application currently does not serve.
- Technical SEO is roughly a one-time hygiene pass. Ranking depends mostly on content quality
  and on backlinks/authority, neither of which lives in this repository.
- `robots.txt` is a request, not a security control. Anything private must stay behind
  authentication, which is why `/api/` exclusions are a courtesy, not the protection.
- Social previews will use a 500×500 logo (`/images/QuantumLLama.png`). A dedicated
  1200×630 share image does not exist yet and has not been invented.

## Known gaps

- the former static `src/platform/web/robots.txt` and `src/platform/web/sitemap.xml` (now deleted) are stale static duplicates:
  they hardcode `https://quantumllama.ai/`, which is **not** the documented deployment origin.
  The new runtime routes are registered first, so crawlers never receive those files; the static
  files should be deleted in a follow-up that is allowed to touch them.
- Canonical, `og:url` and `og:image` are origin-relative until a fixed origin is enforced at the
  reverse proxy/CDN.
- No analytics or measurement script is included here; that is a separate change.
