"""Public release identity without importing broker-backed startup."""
import ast
import json
from pathlib import Path

import pytest

from contextlib import contextmanager
from test_api_route_composition import composed_client

ROOT = Path(__file__).resolve().parents[1]


def version_client():
    return contextmanager(composed_client)(lambda: {"ready_for_ui": True})


def test_product_version_route_matches_package_without_forcing_update():
    expected = json.loads((ROOT / 'package.json').read_text())['version']
    with version_client() as client:
        response = client.get('/api/platform/version')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/json'
    assert response.json() == {
        'version': expected,
        'stable_version': expected,
        'update_required': False,
        'message': 'Nueva versión estable disponible. Por favor actualice para continuar.',
    }


def test_frozen_product_metadata_is_read_from_bundle(tmp_path, monkeypatch):
    from src.product_version import load_product_version
    import sys
    (tmp_path / 'package.json').write_text(json.dumps({'version': '9.8.7'}))
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    assert load_product_version() == '9.8.7'


@pytest.mark.parametrize('version', [None, '', '   ', 123])
def test_invalid_product_version_is_not_silently_invented(tmp_path, monkeypatch, version):
    from src.product_version import load_product_version
    import sys
    (tmp_path / 'package.json').write_text(json.dumps({'version': version}))
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    with pytest.raises(ValueError, match='missing a nonempty version'):
        load_product_version()


def test_fastapi_version_uses_same_product_identity():
    tree = ast.parse((ROOT / 'src/platform/api/main.py').read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == 'FastAPI']
    assert len(calls) == 1
    version = next(k.value for k in calls[0].keywords if k.arg == 'version')
    assert isinstance(version, ast.Name) and version.id == 'PRODUCT_VERSION'
