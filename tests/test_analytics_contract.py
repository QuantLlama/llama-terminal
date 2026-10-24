"""Umami analytics wiring on the public shell."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "src/platform/web/index.html").read_text()
WEBSITE_ID = "03f3d019-7a44-49b8-b4cd-c27ee7691c33"


def test_umami_tracker_is_loaded_from_the_production_domain():
    assert 'src="https://umami.nbmsystemas.com/script.js"' in INDEX
    assert f'data-website-id="{WEBSITE_ID}"' in INDEX
    assert INDEX.count("umami.nbmsystemas.com/script.js") == 1


def test_umami_tracker_is_deferred_and_never_blocks_the_app():
    tag = INDEX[INDEX.index("umami.nbmsystemas.com/script.js") - 200:
                INDEX.index("umami.nbmsystemas.com/script.js") + 200]
    assert "defer" in tag, "a failing analytics host must not block rendering"
    assert "data-auto-track" not in tag or 'data-auto-track="true"' in tag


def test_analytics_never_ships_a_secret_or_a_local_host():
    assert "umami.nbmsystemas.com" in INDEX
    assert "sslip.io" not in INDEX, "tracking must not point at a throwaway host"
    lowered = INDEX.lower()
    for forbidden in ("umami-password", "api_key", "service_role", "localhost:3000"):
        assert forbidden not in lowered
