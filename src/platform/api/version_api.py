"""Public product identity; independent of service startup and broker state."""
from fastapi import APIRouter

from src.product_version import PRODUCT_VERSION

router = APIRouter()

VERSION = PRODUCT_VERSION
STABLE_VERSION = PRODUCT_VERSION
UPDATE_REQUIRED = False
UPDATE_MSG = "Nueva versión estable disponible. Por favor actualice para continuar."


@router.get("/api/platform/version")
async def get_version():
    return {
        "version": VERSION,
        "stable_version": STABLE_VERSION,
        "update_required": UPDATE_REQUIRED,
        "message": UPDATE_MSG,
    }
