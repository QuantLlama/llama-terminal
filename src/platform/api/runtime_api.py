"""Liveness and readiness routes over the existing runtime health provider."""
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse


def create_runtime_router(health_provider: Callable[[], dict[str, Any]]) -> APIRouter:
    """Bind the application's provider without owning health state or lifecycle."""
    router = APIRouter()

    @router.get("/health")
    async def health_check():
        return health_provider()

    @router.get("/api/health")
    async def readiness_check():
        health = health_provider()
        return JSONResponse(
            content=health,
            status_code=200 if health.get("ready_for_ui") is True else 503,
        )

    return router
