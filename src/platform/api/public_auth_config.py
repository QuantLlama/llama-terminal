"""Browser-safe runtime authentication settings, independent of platform startup."""

import base64
import binascii
import json
import os
import re
from urllib.parse import urlsplit

from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter()
_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
_ERROR_SCRIPT = (
    'window.PUBLIC_AUTH_CONFIG = null;\n'
    'throw new Error("Public authentication configuration unavailable; '
    'configure SUPABASE_URL and an anon SUPABASE_ANON_KEY.");\n'
)


def _is_anon_key(key: str) -> bool:
    """Classify a legacy JWT, NOT authenticate it; Supabase verifies its signature.

    Only explicitly anon keys are browser configuration. Unknown key formats and
    privileged roles fail closed. No JWT signing secret is needed or exposed.
    """
    parts = key.split(".")
    if len(parts) != 3 or not all(re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in parts):
        return False
    try:
        decoded = [base64.b64decode(part + "=" * (-len(part) % 4),
                                   altchars=b"-_", validate=True) for part in parts]
        header, payload = (json.loads(part) for part in decoded[:2])
        return (isinstance(header, dict) and header.get("alg") == "HS256"
                and isinstance(payload, dict) and payload.get("role") == "anon")
    except (ValueError, UnicodeError, binascii.Error):
        return False


def _is_public_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return bool(parsed.scheme in {"https", "http"} and parsed.hostname
                    and parsed.port != 0 and not parsed.username and not parsed.password
                    and not parsed.query and not parsed.fragment
                    and not any(ord(char) <= 32 for char in url))
    except ValueError:
        return False


@router.get("/api/public-auth-config.js", include_in_schema=False)
def public_auth_config() -> Response:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not _is_public_url(url) or not _is_anon_key(key):
        return Response(_ERROR_SCRIPT, status_code=503,
                        media_type="application/javascript", headers=_HEADERS)

    # Explicit allowlist: never serialize the environment or administrative keys.
    config = json.dumps({"SUPABASE_URL": url, "SUPABASE_ANON_KEY": key}, ensure_ascii=True)
    for char, escaped in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026")):
        config = config.replace(char, escaped)
    return Response(f"window.PUBLIC_AUTH_CONFIG = {config};\n",
                    media_type="application/javascript", headers=_HEADERS)
