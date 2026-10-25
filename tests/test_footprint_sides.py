"""Side classification for footprint ticks (``_classify_sides``).

In production the ticks frame is built by the bridge path with every field as
``float64``, so ``df["flags"] & 32`` raises::

    TypeError: Cannot perform 'and_' with a dtyped [float64] array and scalar
    of type [bool]

That killed ``backfill_mt5_history`` (footprint loading). The rule under test is
therefore dtype robustness: whatever arrives in ``flags`` must be coerced to a
signed integer before the bitwise test, and the side semantics (bit 32 buy,
bit 64 sell, price-tick fallback for ambiguous volume) must stay identical.

``src/platform/api/footprint_api.py`` imports FastAPI, which this interpreter
does not provide, so the module is imported for real when possible and otherwise
the *shipped* ``_classify_sides`` source is loaded out of the repository file
with ``ast`` and executed. Nothing is duplicated: the code under test is always
the code in the repository.
"""

import ast
import pathlib
import sys

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FOOTPRINT_API = ROOT / "src" / "platform" / "api" / "footprint_api.py"


def _classify_sides_from_source():
    """Load ``_classify_sides`` from the repository file without importing it."""
    source = FOOTPRINT_API.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_classify_sides":
            module = ast.Module(body=[node], type_ignores=[])
            namespace = {"pd": pd}
            exec(compile(module, str(FOOTPRINT_API), "exec"), namespace)
            return namespace["_classify_sides"]
    raise AssertionError(f"_classify_sides not found in {FOOTPRINT_API}")


def _load_classify_sides():
    try:
        from src.platform.api import footprint_api
    except ModuleNotFoundError:
        # FastAPI/pydantic absent in this interpreter: still test the real code.
        return _classify_sides_from_source()
    return footprint_api._classify_sides


@pytest.fixture(scope="module")
def classify_sides():
    return _load_classify_sides()


def _frame(flags, volume=None, last=None):
    data = {"flags": flags}
    data["v"] = list(volume) if volume is not None else [1] * len(flags)
    data["last"] = list(last) if last is not None else [float(i + 1) for i in range(len(flags))]
    return pd.DataFrame(data)


# --- dtype robustness (the production failure) -----------------------------


def test_float_flags_from_the_bridge_do_not_raise(classify_sides):
    """The bridge sends every tick field as float64; that must classify."""
    df = _frame([32.0, 64.0, 0.0], last=[1.0, 2.0, 1.5])

    result = classify_sides(df)

    assert result["is_buy"].tolist() == [True, False, False]
    assert result["is_sell"].tolist() == [False, True, True]


def test_missing_and_unparseable_flags_coerce_to_no_bits(classify_sides):
    """NaN/``None``/text in ``flags`` must not raise and must mean "no bits"."""
    df = _frame(pd.Series([float("nan"), None, "n/a", 32], dtype=object))

    result = classify_sides(df)

    assert result["is_buy"].tolist() == [True, True, True, True]
    assert result["is_sell"].tolist() == [False, False, False, False]


def test_integer_flags_keep_working(classify_sides):
    """The local (integer) path stays on the same semantics."""
    df = _frame([32, 64])

    result = classify_sides(df)

    assert [bool(v) for v in result["is_buy"]] == [True, False]
    assert [bool(v) for v in result["is_sell"]] == [False, True]


# --- side semantics that must not change ------------------------------------


def test_buy_and_sell_bits(classify_sides):
    """Bit 32 is a buy, bit 64 is a sell, both bits set means both."""
    df = _frame([32, 64, 96])

    result = classify_sides(df)

    assert [bool(v) for v in result["is_buy"]] == [True, False, True]
    assert [bool(v) for v in result["is_sell"]] == [False, True, True]


def test_ambiguous_volume_falls_back_to_the_price_tick(classify_sides):
    """With volume but no side bit, the previous tick decides."""
    df = _frame([0, 0, 0], last=[10.0, 11.0, 9.0])

    result = classify_sides(df)

    # First tick compares with itself (>=), then up-tick is buy, down-tick sell.
    assert [bool(v) for v in result["is_buy"]] == [True, True, False]
    assert [bool(v) for v in result["is_sell"]] == [False, False, True]


def test_ambiguous_without_volume_keeps_neither_side(classify_sides):
    """No volume and no side bit: the row must stay unclassified."""
    df = _frame([0, 0], volume=[0, 0], last=[10.0, 11.0])

    result = classify_sides(df)

    assert [bool(v) for v in result["is_buy"]] == [False, False]
    assert [bool(v) for v in result["is_sell"]] == [False, False]


def test_input_frame_is_not_mutated(classify_sides):
    """``_classify_sides`` copies its input; callers rely on that."""
    df = _frame([32.0, 64.0])

    result = classify_sides(df)

    assert list(df.columns) == ["flags", "v", "last"]
    assert set(result.columns) >= {"is_buy", "is_sell"}


# --- source shape: the coercion must happen before the bitwise test ---------


def test_source_coerces_flags_before_the_bitwise_test():
    """A future edit must not put the raw column back under ``&``."""
    source = FOOTPRINT_API.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_classify_sides"
    )
    body = ast.get_source_segment(source, function) or ""

    assert 'errors="coerce"' in body, body
    assert "pd.to_numeric(" in body, body
    assert "fillna(0)" in body, body
    assert "astype(" in body, body
    assert 'df["flags"] &' not in body, body
