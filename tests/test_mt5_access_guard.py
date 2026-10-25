"""S3 guard: API modules must not import the Windows-only ``MetaTrader5``.

Production answered ``ModuleNotFoundError: No module named 'MetaTrader5'``
because handlers under ``src/platform/api/`` imported the package directly. The
package only exists on Windows/Wine, so inside the Linux container those imports
raise: ``POST /api/order`` answered 500 and every MT5 tape stayed mute.

The rule has no exceptions: nothing under ``src/platform/api/`` imports the
package, and every module that needs MT5 goes through ``src.live.mt5_access``.
The scan reads the sources with ``ast`` and never imports the API modules
themselves, because ``fastapi``/``pydantic`` are not installed in this
environment.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "src" / "platform" / "api"
ACCESS_MODULE = ROOT / "src" / "live" / "mt5_access.py"

#: Modules converted by this change; each one must use the access layer.
MIGRATED_MODULES = ("main.py", "footprint_api.py", "backtesting_api.py")

PACKAGE = "MetaTrader5"


def _api_sources():
    return sorted(path for path in API_DIR.rglob("*.py"))


def _imported_names(node):
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    return [node.module or ""]


def _import_sites(tree):
    """Line numbers of every direct import of the package in one module."""
    sites = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if any(name.split(".")[0] == PACKAGE for name in _imported_names(node)):
                sites.append(node.lineno)
    return sites


def _offenders():
    """``{relative path: [lineno, ...]}`` for the whole API package."""
    found = {}
    for path in _api_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        sites = _import_sites(tree)
        if sites:
            found[str(path.relative_to(API_DIR)).replace("\\", "/")] = sites
    return found


def test_no_api_module_imports_metatrader5():
    offenders = _offenders()

    assert offenders == {}, (
        "no module under src/platform/api/ may import MetaTrader5, guarded or "
        f"not; use src.live.mt5_access instead: {offenders}"
    )


def test_migrated_modules_use_the_access_layer():
    for name in MIGRATED_MODULES:
        source = (API_DIR / name).read_text(encoding="utf-8")
        assert "mt5_access" in source, f"{name} does not use the single access module"


def test_access_layer_exists_and_owns_the_import():
    assert ACCESS_MODULE.is_file()
    source = ACCESS_MODULE.read_text(encoding="utf-8")
    # The package name is only ever assembled at runtime, never imported.
    assert "importlib.import_module" in source
    assert PACKAGE in source
