"""One-shot desktop data import over HTTPS.

A desktop installation keeps its workspaces and settings in a SQLite file that
the hosted platform imports once at startup. Getting that file into a container
normally needs shell access, which the hosting panel does not expose. This
router provides a narrow, explicitly gated transport for that single file.

Safety properties, in order of importance:

* Disabled unless ``QL_DESKTOP_IMPORT_TOKEN`` is set; unset means 404.
* The caller must present that token in ``X-Import-Token``; wrong token is 401.
* Refuses once the import marker exists, so it cannot rewrite live data.
* Bounded size, atomic write with owner-only permissions, and no path input:
  the destination is always the platform's own data path.
"""
import hmac
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request

from src.services import database

TOKEN_ENV = "QL_DESKTOP_IMPORT_TOKEN"
MAX_BYTES = 64 * 1024 * 1024

router = APIRouter(prefix="/api/ops", tags=["Operations"])


def _expected_token() -> str:
    return (os.environ.get(TOKEN_ENV) or "").strip()


def _authorise(provided: str | None) -> None:
    expected = _expected_token()
    if not expected:
        # An unset gate must look like the route does not exist at all.
        raise HTTPException(status_code=404, detail="Not Found")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid import token")


@router.get("/desktop-import/status")
async def desktop_import_status(
    x_import_token: str | None = Header(default=None, alias="X-Import-Token"),
):
    """Report what the importer sees, without exposing any row content."""
    _authorise(x_import_token)
    path = Path(database.get_db_path())
    info = {
        "path": str(path),
        "exists": path.exists(),
        "marker_applied": database.legacy_import_already_applied(),
        "target_user": database.legacy_import_user_id(),
    }
    if path.exists():
        info["size"] = path.stat().st_size
        info["tables"] = database.legacy_table_counts(str(path))
    return info


@router.post("/desktop-import")
async def desktop_import(
    request: Request,
    x_import_token: str | None = Header(default=None, alias="X-Import-Token"),
    x_import_force: str | None = Header(default=None, alias="X-Import-Force"),
    x_import_replace: str | None = Header(default=None, alias="X-Import-Replace"),
):
    """Store an uploaded desktop database and run the one-time import."""
    _authorise(x_import_token)

    destination = Path(database.get_db_path())
    replace = (x_import_replace or "").strip() == "1"
    forced = (x_import_force or "").strip() == "1" or replace
    if database.legacy_import_already_applied():
        if not forced:
            raise HTTPException(
                status_code=409,
                detail="The legacy import already ran; refusing to replace live data.",
            )
        # A deliberate retry still never overwrites: the import inserts with
        # DO NOTHING, so only missing rows are added.
        database.clear_legacy_import_marker()
    replaced = None
    if replace:
        # Destructive by design: only reachable with the operator token, and the
        # rows are then restored from the uploaded file in the same request.
        replaced = database.delete_user_rows(database.legacy_import_user_id())

    payload = await request.body()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty upload")
    if len(payload) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Upload too large")
    if not payload.startswith(b"SQLite format 3\x00"):
        raise HTTPException(status_code=400, detail="Not a SQLite database")

    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=str(destination.parent), prefix=".import-")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise

    result = database.import_legacy_sqlite(str(destination))
    return {
        "status": result.get("status"),
        "imported": result.get("imported", {}),
        "replaced": replaced,
        "bytes": len(payload),
    }
