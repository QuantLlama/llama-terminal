"""Bounded startup retry for the market-data connection and order gateway.

The platform logs that it will retry a failed broker connection, but the order
gateway was only started when the very first attempt succeeded, so a transient
failure at boot left it stopped for the life of the process.
"""
import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


async def connect_with_retry(
    engine: Any,
    gateway: Any,
    attempts: int = 12,
    delay: float = 10.0,
    sleep: Callable[[float], Any] = asyncio.sleep,
    executor: Any = None,
) -> bool:
    """Start the engine, retrying, and bring the gateway up once it connects.

    Returns True as soon as the engine reports success. Every failure is retried
    up to ``attempts`` times; the gateway is started only after a successful
    connection and only when it is not already running.
    """
    loop = asyncio.get_event_loop()
    run = loop.run_in_executor
    for attempt in range(1, attempts + 1):
        try:
            started = bool(await run(executor, engine.start))
        except Exception as exc:  # a failing connector must not kill startup
            logger.warning("Market data attempt %s/%s raised: %s", attempt, attempts, exc)
            started = False
        if started:
            if gateway is not None and not getattr(gateway, "is_running", False):
                try:
                    gateway.start()
                except Exception as exc:
                    logger.error("Order gateway failed to start: %s", exc)
                    return True
            logger.info("Market data connected on attempt %s", attempt)
            return True
        logger.warning("Market data attempt %s/%s failed", attempt, attempts)
        if attempt < attempts:
            await sleep(delay)
    logger.error("Market data could not connect after %s attempts", attempts)
    return False
