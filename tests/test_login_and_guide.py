"""Login redesign and in-app setup guide contract.

The login form and the onboarding guide are browser components with no build
step (``text/babel`` scripts using ``React.createElement``), so every rule that
matters is asserted statically from the real files: the auth flow and strings
the login must keep, the accessibility affordances it adds, the bridge facts
the guide must state, and the drift guards that tie the documented defaults to
the modules that actually own them.

No browser, bundler or network is involved. The MT5 bridge defaults are read
from ``mt5_bridge_auth`` and ``mt5_api_connector`` so the guide cannot document
a value the code does not use.
"""
import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src" / "platform" / "web"
LOGIN = WEB / "components" / "LoginModal.js"
GUIDE = WEB / "components" / "SetupGuide.js"
INDEX = WEB / "index.html"
DOC = ROOT / "docs" / "ONBOARDING.md"
BRIDGE_AUTH = ROOT / "src" / "live" / "mt5_bridge_auth.py"
CONNECTOR = ROOT / "src" / "live" / "mt5_api_connector.py"

PRICING_URL = "https://llamaterminal.nbmsystemas.com/#pricing"
LOGO_PATH = "/images/QuantumLLama.png"

# Anything that looks like a committed credential rather than a placeholder.
SECRET_PATTERNS = (
    r"\b(?:sk|pk|rk)_(?:live|test)?_?[A-Za-z0-9]{16,}",
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\bgh[pousr]_[A-Za-z0-9]{20,}",
    r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    r"MT5_BRIDGE_TOKEN\s*=\s*[A-Za-z0-9_-]{20,}",
    r"[A-Za-z0-9_-]{44,}",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_without_newline_translation(path: Path) -> str:
    """Decode the file as stored, so CRLF assertions see the real bytes."""
    return path.read_bytes().decode("utf-8")


def _module_constant(path: Path, name: str):
    """Return the literal value of a module-level assignment in ``path``."""
    tree = ast.parse(_read(path))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is missing from {path.name}")


BRIDGE_DEFAULTS = (
    ("MT5_BRIDGE_BIND", str(_module_constant(BRIDGE_AUTH, "DEFAULT_BIND"))),
    ("MT5_BRIDGE_PORT", str(_module_constant(BRIDGE_AUTH, "DEFAULT_PORT"))),
    ("MT5_BRIDGE_URL", str(_module_constant(CONNECTOR, "DEFAULT_BRIDGE_URL"))),
)


@pytest.fixture(scope="module")
def login_src():
    assert LOGIN.is_file(), "src/platform/web/components/LoginModal.js is missing"
    return _read(LOGIN)


@pytest.fixture(scope="module")
def guide_src():
    assert GUIDE.is_file(), "src/platform/web/components/SetupGuide.js is missing"
    return _read(GUIDE)


@pytest.fixture(scope="module")
def doc_text():
    assert DOC.is_file(), "docs/ONBOARDING.md is missing"
    return _read(DOC)


# --------------------------------------------------------------------------
# Login: the auth flow that must not change
# --------------------------------------------------------------------------

def test_login_signs_in_through_supabase(login_src):
    assert "window.supabase.auth.signInWithPassword" in login_src
    assert re.search(r"signInWithPassword\(\{\s*email,\s*password\s*\}\)", login_src)


def test_login_checks_the_subscription_endpoint_with_the_access_token(login_src):
    assert "/api/auth/session" in login_src
    assert re.search(
        r"'Authorization':\s*`Bearer \$\{result\.data\.session\.access_token\}`", login_src
    )
    assert "is_subscribed" in login_src
    assert "signOut" in login_src


def test_login_still_allows_access_when_the_subscription_check_is_unavailable(login_src):
    # Both fallbacks (non-OK response and network error) keep the legacy behaviour.
    assert login_src.count("allowing login") >= 2
    assert "sRes.ok" in login_src


def test_login_keeps_the_remember_me_storage_keys(login_src):
    for key in ("ql_email", "ql_password", "ql_remember"):
        assert key in login_src, f"{key} storage key dropped"
    assert re.search(r"setItem\('ql_email'", login_src)
    assert re.search(r"setItem\('ql_password'", login_src)
    assert re.search(r"setItem\('ql_remember', 'true'\)", login_src)
    assert re.search(r"setItem\('ql_remember', 'false'\)", login_src)
    assert re.search(r"removeItem\('ql_password'\)", login_src)


def test_login_reports_the_session_to_the_host(login_src):
    assert "onLogin(result.data.session)" in login_src


def test_login_keeps_the_exact_error_strings(login_src):
    assert "'Invalid credentials'" in login_src
    assert re.search(
        r"Restricted access\. PREMIUM account required\. \(\$\{reason\}\)", login_src
    )
    assert "err.message === 'Invalid login credentials'" in login_src


# --------------------------------------------------------------------------
# Login: the improvements the owner asked for
# --------------------------------------------------------------------------

def test_login_error_region_is_an_alert(login_src):
    assert re.search(r'role:\s*"alert"', login_src)
    assert re.search(r'error\s*&&', login_src)


def test_login_has_a_password_reveal_toggle(login_src):
    assert "showPassword" in login_src
    assert re.search(r'type:\s*showPassword\s*\?\s*"text"\s*:\s*"password"', login_src)
    assert re.search(r'aria-label":\s*showPassword\s*\?\s*"Hide password"\s*:\s*"Show password"', login_src)
    assert "fa-eye" in login_src


def test_login_has_visible_labels_and_focus_rings(login_src):
    assert re.search(r'htmlFor:\s*"login-email"', login_src)
    assert re.search(r'htmlFor:\s*"login-password"', login_src)
    assert re.search(r'id:\s*"login-email"', login_src)
    assert re.search(r'id:\s*"login-password"', login_src)
    assert "focus-visible:ring-2" in login_src


def test_login_shows_an_inline_spinner_while_signing_in(login_src):
    assert "animate-spin" in login_src
    assert re.search(r'aria-busy', login_src)
    assert "SIGN IN" in login_src


def test_login_is_a_two_panel_layout_that_collapses_to_one_column(login_src):
    assert "grid-cols-1" in login_src
    assert "lg:grid-cols-2" in login_src


def test_login_uses_readable_type(login_src):
    tiny = re.findall(r"text-\[(?:8|9|10)px\]", login_src)
    assert not tiny, f"login still renders body text at 9-10px: {tiny}"


def test_login_keeps_the_premium_link_and_the_logo_asset(login_src):
    assert PRICING_URL in login_src
    assert 'target: "_blank"' in login_src
    assert 'rel: "noopener noreferrer"' in login_src
    assert "PREMIUM PLANS" in login_src
    assert LOGO_PATH in login_src


def test_login_opens_the_setup_guide(login_src):
    assert "Configurar mi sistema" in login_src
    assert re.search(r"setGuideOpen\(true\)", login_src)
    assert "window.SetupGuide" in login_src
    assert re.search(r"setGuideOpen\(false\)", login_src)


# --------------------------------------------------------------------------
# SetupGuide: modal behaviour
# --------------------------------------------------------------------------

def test_setup_guide_is_published_as_a_window_global(guide_src):
    assert "window.SetupGuide = SetupGuide" in guide_src
    assert "const SetupGuide = ({ onClose })" in guide_src


def test_setup_guide_closes_on_escape(guide_src):
    assert re.search(r"key\s*===\s*'Escape'", guide_src)
    assert "onClose()" in guide_src


def test_setup_guide_closes_on_a_backdrop_click(guide_src):
    assert re.search(r"e\.target\s*===\s*e\.currentTarget", guide_src)
    assert re.search(r"onMouseDown", guide_src)


def test_setup_guide_close_button_is_labelled(guide_src):
    assert re.search(r'aria-label":\s*"Close setup guide"', guide_src)


def test_setup_guide_traps_keyboard_focus(guide_src):
    assert re.search(r"key\s*===\s*'Tab'", guide_src)
    assert "preventDefault" in guide_src
    assert "getFocusable" in guide_src
    assert "panelRef" in guide_src
    assert re.search(r'addEventListener\("keydown"', guide_src)
    assert re.search(r'removeEventListener\("keydown"', guide_src)
    # Focus moves back inside the panel at both ends of the tab order.
    assert re.search(r"last\.focus\(\)", guide_src)
    assert re.search(r"first\.focus\(\)", guide_src)


# --------------------------------------------------------------------------
# SetupGuide: the facts it must state
# --------------------------------------------------------------------------

def test_setup_guide_is_reachable_from_the_login_screen_of_the_page():
    text = _read_without_newline_translation(INDEX)
    assert "components/SetupGuide.js" in text
    assert text.index("components/SetupGuide.js") < text.index("components/LoginModal.js")
    # Global order matters: the login looks the component up on window.
    assert re.search(
        r'<script type="text/babel" src="/?components/SetupGuide\.js\?v=[\d.]+"></script>\r\n', text
    )


def test_page_defines_the_entrance_animation_the_components_use():
    text = _read_without_newline_translation(INDEX)
    assert "@keyframes ql-rise" in text


@pytest.mark.parametrize("var,default", BRIDGE_DEFAULTS)
def test_guide_documents_each_env_var_with_its_real_default(guide_src, var, default):
    row = re.search(r"\[\s*'%s',\s*'%s'" % (var, re.escape(default)), guide_src)
    assert row, f"{var} must be documented with the default the code uses ({default!r})"


def test_guide_documents_the_token_requirement(guide_src):
    assert re.search(r"\[\s*'MT5_BRIDGE_TOKEN',\s*'\(unset\)'", guide_src)
    assert re.search(r"mandatory", guide_src, re.IGNORECASE)
    assert "0.0.0.0" in guide_src
    assert "127.0.0.1" in guide_src


def test_guide_keeps_the_verified_commands_and_endpoints(guide_src):
    for fragment in (
        "secrets.token_urlsafe(32)",
        "setup_env.sh",
        "setup_env.bat",
        "requirements.txt",
        "start_mt5_server.bat",
        'wine python -m uvicorn mt5_server:app --host "$MT5_BRIDGE_BIND" --port 8081',
        "MT5_BRIDGE_BIND=0.0.0.0",
        "X-Bridge-Token",
        "/api/balance",
        "/api/health",
        "mt5_status",
        "market_data",
        "ONLINE",
        "connected",
        "Tailscale",
        "mt5_server.py",
        "8081",
    ):
        assert fragment in guide_src, f"guide lost the verified fragment: {fragment}"


def test_guide_does_not_invent_a_bridge_health_route(guide_src):
    # mt5_server.py exposes no /health route; the documented local probe is
    # /api/balance with the bridge token, which the bridge really serves.
    assert "8081/health" not in guide_src


def test_guide_has_seven_numbered_steps(guide_src):
    numbers = [int(n) for n in re.findall(r"\{\s*n:\s*(\d+),", guide_src)]
    assert numbers == [1, 2, 3, 4, 5, 6, 7]


def test_guide_points_at_the_accounts_section_for_crypto_keys(guide_src):
    assert "Accounts" in guide_src
    assert "API key" in guide_src


# --------------------------------------------------------------------------
# SetupGuide: illustrations
# --------------------------------------------------------------------------

def test_guide_has_at_least_three_inline_svg_illustrations(guide_src):
    assert guide_src.count("<svg") >= 3
    assert guide_src.count("</svg>") >= 3
    assert "dangerouslySetInnerHTML" in guide_src
    assert 'xmlns="http://www.w3.org/2000/svg"' in guide_src
    assert re.search(r'role"?\s*:\s*"img"', guide_src)
    assert re.search(r'aria-hidden":\s*"true"', guide_src)


def test_guide_uses_no_external_or_binary_assets(guide_src):
    assert "https://" not in guide_src
    assert not re.search(r"<img\b", guide_src)
    assert not re.search(r"\bsrc\s*:", guide_src)
    assert not re.search(r"\.(?:png|jpe?g|gif|webp)\b", guide_src)
    assert "url(http" not in guide_src


# --------------------------------------------------------------------------
# Documentation and hygiene
# --------------------------------------------------------------------------

def test_onboarding_doc_links_the_runbooks_instead_of_copying_them(doc_text):
    assert "deploy/MT5_BRIDGE.md" in doc_text
    assert "docs/CLOUD.md" in doc_text
    assert doc_text.count("```mermaid") >= 1


def test_onboarding_doc_covers_the_same_steps(doc_text):
    for fragment in (
        "MT5_BRIDGE_BIND",
        "MT5_BRIDGE_PORT",
        "MT5_BRIDGE_TOKEN",
        "MT5_BRIDGE_URL",
        "/api/health",
        "mt5_status",
        "ONLINE",
        "Tailscale",
    ):
        assert fragment in doc_text, f"onboarding doc lost: {fragment}"
    assert len(re.findall(r"^### Step \d", doc_text, re.MULTILINE)) == 7


@pytest.mark.parametrize("path", [LOGIN, GUIDE, DOC], ids=["login", "guide", "doc"])
def test_committed_files_contain_no_secret_shaped_literal(path):
    text = _read(path)
    for pattern in SECRET_PATTERNS:
        match = re.search(pattern, text)
        assert not match, f"{path.name} contains a secret-shaped literal: {match.group(0)!r}"


def test_index_html_still_uses_crlf_line_endings():
    raw = INDEX.read_bytes()
    assert b"\r\n" in raw
    assert raw.count(b"\r\n") > 100
