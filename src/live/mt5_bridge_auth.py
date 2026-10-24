"""Transport security for the MT5 HTTP bridge.

The bridge exposes broker access (orders included), so when it is reachable
beyond loopback it must require a shared token. The local default stays
unauthenticated on 127.0.0.1 to preserve the desktop workflow.
"""

import hmac
import logging
import os

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

TOKEN_ENV = "MT5_BRIDGE_TOKEN"
BIND_ENV = "MT5_BRIDGE_BIND"
PORT_ENV = "MT5_BRIDGE_PORT"
TOKEN_HEADER = "x-bridge-token"

DEFAULT_BIND = "127.0.0.1"
DEFAULT_PORT = 8081


def bridge_token() -> str:
    return os.getenv(TOKEN_ENV, "").strip()


def bridge_bind() -> tuple:
    """Return the (host, port) the bridge should listen on."""
    host = os.getenv(BIND_ENV, DEFAULT_BIND).strip() or DEFAULT_BIND
    raw_port = os.getenv(PORT_ENV, str(DEFAULT_PORT)).strip() or str(DEFAULT_PORT)
    try:
        port = int(raw_port)
    except ValueError:
        logger.warning("Invalid %s=%r, falling back to %s", PORT_ENV, raw_port, DEFAULT_PORT)
        port = DEFAULT_PORT
    return host, port


async def require_bridge_token(request: Request, call_next):
    expected = bridge_token()
    if not expected:
        return await call_next(request)

    provided = request.headers.get(TOKEN_HEADER, "")
    if not hmac.compare_digest(provided, expected):
        logger.warning("Rejected bridge request to %s without a valid token", request.url.path)
        return JSONResponse({"detail": "invalid bridge token"}, status_code=401)

    return await call_next(request)
