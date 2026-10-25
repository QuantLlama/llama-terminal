"""A compiled module next to its source silently replaces it at import time.

This repository has shipped stale ``*.so`` build artefacts inside ``src/``
before. Under CPython they take precedence over the ``.py`` file with the same
name, so a test run can execute months-old compiled code and still report
green — which is exactly how a broken change once looked healthy locally and
failed in CI.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPILED_SUFFIXES = (".so", ".pyd")


def _shadowing_pairs():
    pairs = []
    for compiled in ROOT.rglob("*"):
        if compiled.suffix not in COMPILED_SUFFIXES or ".git" in compiled.parts:
            continue
        # "database.cpython-311-x86_64-linux-gnu.so" shadows "database.py"
        stem = compiled.name.split(".")[0]
        source = compiled.parent / f"{stem}.py"
        if source.exists():
            pairs.append((compiled, source))
    return pairs


def test_no_compiled_module_shadows_a_python_source():
    pairs = _shadowing_pairs()
    assert pairs == [], (
        "these compiled modules shadow their Python source and would be imported "
        "instead of it:\n"
        + "\n".join(
            f"  {comp.relative_to(ROOT)} shadows {src.relative_to(ROOT)}"
            for comp, src in pairs
        )
        + "\nMove them out of the source tree (build output belongs under build/)."
    )
