"""Every runtime import of the container image must be declared.

The production image installs `requirements.deploy.txt` only. A storage driver
that exists in `requirements.txt` but not there fails at request time, not at
build time, which is how a missing `psycopg2` reached production.
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

IMPORT_TO_DISTRIBUTION = {
    "psycopg2": "psycopg2-binary",
    "supabase": "supabase",
    "fastapi": "fastapi",
    "pandas": "pandas",
    "numpy": "numpy",
}


def _declared(filename: str) -> set:
    names = set()
    for line in (ROOT / filename).read_text().splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        names.add(re.split(r"[=<>!\[; ]", line)[0].lower())
    return names


def _imported_in(path: Path) -> set:
    tree = ast.parse(path.read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def test_container_requirements_declare_every_storage_driver():
    deploy = _declared("requirements.deploy.txt")
    for module, distribution in IMPORT_TO_DISTRIBUTION.items():
        source = ROOT / "src/services/user_repository.py"
        if module in _imported_in(source):
            assert distribution.lower() in deploy, (
                f"{module} is imported by src/services/user_repository.py but "
                f"{distribution} is missing from requirements.deploy.txt, which is "
                "what the production image installs"
            )


def test_deploy_requirements_are_not_empty_and_stay_minimal():
    deploy = _declared("requirements.deploy.txt")
    assert "fastapi" in deploy and "uvicorn" in deploy
    # The container must not drag the training stack in.
    for heavy in ("torch", "transformers", "xgboost"):
        assert heavy not in deploy


def test_image_ships_the_tools_offsite_backup_needs():
    """The nightly backup runs inside the container, so its tools must be in the image."""
    dockerfile = (ROOT / "Dockerfile").read_text()
    for package in ("postgresql-client", "gzip"):
        assert package in dockerfile, (
            f"{package} is required by scripts/backup_to_r2.py at runtime but is not "
            "installed in the image"
        )
