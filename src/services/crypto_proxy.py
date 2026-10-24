"""Egress proxy support for crypto exchanges.

Some venues block whole regions (Binance answers HTTP 451 from the cloud
provider's US region). When CRYPTO_HTTP_PROXY is set, crypto traffic is routed
through that proxy, which can be a tailnet relay to an allowed network.
"""

import logging
import os

logger = logging.getLogger(__name__)

PROXY_ENV = "CRYPTO_HTTP_PROXY"


def http_proxy_url():
    return os.getenv(PROXY_ENV, "").strip() or None


def apply_proxy(exchange):
    """Route an exchange through the configured proxy, when there is one."""
    url = http_proxy_url()
    if not url or exchange is None:
        return exchange
    try:
        exchange.proxies = {"http": url, "https": url}
        logger.info("Crypto traffic routed through proxy %s", url)
    except Exception as exc:  # pragma: no cover - ccxt specific
        logger.error("Could not apply crypto proxy %s: %s", url, exc)
    return exchange
