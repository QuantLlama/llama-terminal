"""The cloud image must ship torch because training imports it unconditionally.

``train.py`` starts with ``import torch``. When the image was built with
``WITH_TORCH=false`` the spawned training process died instantly with
``ModuleNotFoundError: No module named 'torch'`` while ``POST /api/algo/start``
answered 200, so the failure was invisible from the UI: the endpoint reported
"Training started" and nothing happened.

The contract is structural: it ties the image default to the reason it exists.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
TRAIN = ROOT / "train.py"


def test_training_really_needs_torch():
    """If this ever stops being true, the image default can be revisited."""
    source = TRAIN.read_text()

    assert re.search(r"^import torch$", source, re.MULTILINE), (
        "train.py no longer imports torch at module level; revisit the image default"
    )


def test_cloud_image_ships_torch_by_default():
    dockerfile = DOCKERFILE.read_text()

    assert re.search(r"^ARG WITH_TORCH=true$", dockerfile, re.MULTILINE), (
        "the image must include torch: training runs in the container and dies "
        "without it"
    )
    assert "pip install" in dockerfile and "torch==" in dockerfile, (
        "WITH_TORCH must actually install a pinned torch build"
    )
