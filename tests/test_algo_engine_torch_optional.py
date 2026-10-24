"""Regression tests: the algo engine must import without torch installed.

The cloud deployment image does not bundle torch, so importing the module
must degrade to HAS_TORCH = False instead of raising at import time.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_algo_engine_imports_without_torch():
    script = textwrap.dedent(
        """
        import importlib.abc
        import sys

        class BlockTorch(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "torch" or fullname.startswith("torch."):
                    raise ImportError("torch blocked by regression test")
                return None

        sys.meta_path.insert(0, BlockTorch())

        import src.services.algo_engine.engine as engine

        assert engine.HAS_TORCH is False, "HAS_TORCH must be False when torch is missing"
        assert engine.torch is None, "torch must be None when torch is missing"
        print("ALGO_ENGINE_TORCH_OPTIONAL_OK")
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, (
        "Importing the algo engine without torch failed:\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "ALGO_ENGINE_TORCH_OPTIONAL_OK" in result.stdout
