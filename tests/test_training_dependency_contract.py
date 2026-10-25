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


# ── market-data downloader ──────────────────────────────────────────────────

REQUIREMENTS = (ROOT / "requirements.deploy.txt", ROOT / "requirements.txt")


def test_pinned_yfinance_can_still_read_yahoo():
    """yfinance 0.2.40 fails with JSONDecodeError against today's Yahoo endpoints.

    The pinned version must be one that goes through the modern client, and that
    client needs curl_cffi: without it every training run dies in load_data with
    \"No data found for ticker\" while the network is perfectly healthy.
    """
    for path in REQUIREMENTS:
        text = path.read_text()
        match = re.search(r"^yfinance==(\d+)\.(\d+)\.(\d+)", text, re.MULTILINE)
        assert match, f"{path.name} must pin yfinance"
        major, minor, patch = (int(part) for part in match.groups())
        assert (major, minor, patch) >= (0, 2, 54), (
            f"{path.name} pins yfinance {major}.{minor}.{patch}, which cannot parse "
            "the current Yahoo responses"
        )
        assert re.search(r"^curl_cffi==", text, re.MULTILINE), (
            f"{path.name} must pin curl_cffi: the modern yfinance client needs it"
        )


def test_no_modules_pass_a_session_to_yfinance():
    """``session=`` was removed: the modern client owns its own transport."""
    offenders = []
    for path in (ROOT / "src").rglob("*.py"):
        for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r"yf\.(Ticker|download)\(.*\bsession\s*=", stripped):
                offenders.append(f"{path.relative_to(ROOT)}:{number}")

    assert offenders == [], (
        "these calls pass a removed yfinance argument and fail silently: "
        f"{offenders}"
    )
