"""The cache helper is called from API code that cannot be imported here.

CI validates source shape, not execution: that is exactly how a call passing a
fifth positional to a four-argument helper reached production and turned
/api/deals into a 500 on every request. This reads the real source and checks the
call arity, which is the one thing a py_compile cannot see.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src" / "platform" / "api" / "main.py"
HELPER = ROOT / "src" / "platform" / "api" / "deals_cache.py"

POSITIONAL = 4


def _helper_arity() -> int:
    tree = ast.parse(HELPER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "cached":
            return len(node.args.args)
    raise AssertionError("cached() is missing from deals_cache.py")


def _cached_calls():
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "cached":
            yield node


def test_helper_keeps_its_documented_arity():
    assert _helper_arity() == POSITIONAL


def test_every_call_passes_exactly_the_positional_arguments_the_helper_takes():
    arity = _helper_arity()
    calls = list(_cached_calls())
    assert calls, "no cached() call found in main.py"

    offenders = [
        f"line {call.lineno}: {len(call.args)} positional arguments"
        for call in calls
        if len(call.args) != arity
    ]

    assert offenders == [], (
        f"cached() takes {arity} positional arguments; a mismatch is a TypeError at "
        f"runtime, and py_compile cannot see it: {offenders}"
    )


def test_the_tenant_reaches_the_producer_by_closure_not_by_position():
    source = MAIN.read_text(encoding="utf-8")
    assert "def _produce_deals_payload():" in source, (
        "the tenant must be bound in a zero-argument producer; passing it as an "
        "extra positional is what broke /api/deals"
    )
