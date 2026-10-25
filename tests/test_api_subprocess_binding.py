"""The API module must keep the stdlib ``subprocess`` module bound to its name.

``src/platform/api/main.py`` starts training and live processes with
``subprocess.Popen``. A stray ``from asyncio import subprocess`` rebound that name
to ``asyncio.subprocess``, which has no ``Popen`` (asyncio exposes
``create_subprocess_exec`` instead), so ``POST /api/algo/start`` answered
``500 {"detail": "Spawn failed: module 'asyncio.subprocess' has no attribute
'Popen'"}`` and training could not start at all.

The check is structural on purpose: importing the API module needs the full
runtime dependency set, and this contract is about the import graph, not about
running the server.
"""
import ast
from pathlib import Path

MAIN = Path(__file__).resolve().parents[1] / "src/platform/api/main.py"


def _module():
    return ast.parse(MAIN.read_text())


def test_main_binds_the_stdlib_subprocess_module():
    """No import may rebind ``subprocess`` to something else."""
    rebound = []
    for node in ast.walk(_module()):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "subprocess" and alias.asname is None:
                    rebound.append((node.lineno, node.module))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("subprocess") and alias.asname == "subprocess":
                    rebound.append((node.lineno, alias.name))

    assert rebound == [], (
        "main.py rebinds the name 'subprocess' to another module; "
        f"subprocess.Popen then disappears: {rebound}"
    )


def test_main_imports_subprocess_for_its_process_helpers():
    """The stdlib module has to stay imported because the module spawns processes."""
    imported = {
        alias.name
        for node in ast.walk(_module())
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    uses_popen = any(
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "subprocess"
        and node.attr == "Popen"
        for node in ast.walk(_module())
    )

    assert uses_popen, "the module is expected to spawn processes"
    assert "subprocess" in imported, "spawning processes needs the stdlib subprocess import"
