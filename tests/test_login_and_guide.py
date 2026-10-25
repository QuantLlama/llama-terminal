"""Login redesign and in-app setup guide contract.

The login form and the onboarding guide are browser components with no build
step (``text/babel`` scripts using ``React.createElement``), so every rule that
matters is asserted statically from the real files: the auth flow the login must
keep, the copy it renders, the accessibility affordances it adds, the bridge
facts the guide must state, and the drift guards that tie the documented
defaults to the modules that actually own them.

Both surfaces are bilingual, so the copy lives in ``loginI18n.js`` and
``setupGuideContent.js``. A rule about a visible string therefore asserts two
things: the component renders the dictionary key, and every language defines it.
Reading the component alone would prove neither.

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
I18N = WEB / "lib" / "loginI18n.js"
CONTENT = WEB / "lib" / "setupGuideContent.js"
INDEX = WEB / "index.html"
DOC = ROOT / "docs" / "ONBOARDING.md"
BRIDGE_AUTH = ROOT / "src" / "live" / "mt5_bridge_auth.py"
CONNECTOR = ROOT / "src" / "live" / "mt5_api_connector.py"

PRICING_URL = "https://llamaterminal.nbmsystemas.com/#pricing"
LOGO_PATH = "/images/QuantumLLama.png"
LANGUAGES = ("es", "en")

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


def _language_block(src: str, language: str) -> str:
    """Return the body of the ``<language>: { ... }`` dictionary in ``src``.

    Both dictionaries are plain objects with one language per top-level key and a
    fixed indentation, so the block boundaries are unambiguous.
    """
    try:
        start = src.index(f"    {language}: {{")
    except ValueError as exc:  # pragma: no cover - a missing language is a bug
        raise AssertionError(f"the {language} dictionary is missing from the file") from exc
    # The last language closes without a trailing comma, so cut at the brace.
    end = re.search(r"\n    \}", src[start:])
    assert end, f"the {language} dictionary is not closed"
    return src[start:start + end.start()]


def _copy(src: str, language: str, key: str) -> str:
    """Return the copy of ``key`` for ``language``, failing if it is absent."""
    block = _language_block(src, language)
    # Dotted keys are quoted; the guide's plain keys are bare identifiers.
    match = re.search(r"(?:'%s'|\b%s):\s*'([^']*)'" % (re.escape(key), re.escape(key)), block)
    assert match, f"{key} is missing from the {language} dictionary"
    value = match.group(1)
    assert value.strip(), f"{key} is empty in the {language} dictionary"
    return value


def _copy_in_every_language(src: str, key: str):
    return {language: _copy(src, language, key) for language in LANGUAGES}


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
def i18n_src():
    assert I18N.is_file(), "src/platform/web/lib/loginI18n.js is missing"
    return _read(I18N)


@pytest.fixture(scope="module")
def content_src():
    assert CONTENT.is_file(), "src/platform/web/lib/setupGuideContent.js is missing"
    return _read(CONTENT)


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


# --------------------------------------------------------------------------
# Login: the copy, which now lives in the dictionary
# --------------------------------------------------------------------------

def test_login_keeps_the_exact_error_strings(login_src, i18n_src):
    assert "err.message === 'Invalid login credentials'" in login_src
    assert _copy(i18n_src, "en", "error.invalidCredentials") == "Invalid credentials."
    assert "PREMIUM" in _copy(i18n_src, "es", "error.subscriptionRequired")
    assert "Acceso restringido" in _copy(i18n_src, "es", "error.subscriptionRequired")
    # The reason code the endpoint returns is still shown, not swallowed.
    assert re.search(r"key:\s*'error\.subscriptionRequired',\s*detail:\s*reason", login_src)
    assert "error.detail" in login_src


def test_login_has_a_password_reveal_toggle(login_src, i18n_src):
    assert "showPassword" in login_src
    assert re.search(r'type:\s*showPassword\s*\?\s*"text"\s*:\s*"password"', login_src)
    assert re.search(
        r"t\(showPassword\s*\?\s*'action\.hidePassword'\s*:\s*'action\.showPassword'\)", login_src
    )
    assert _copy(i18n_src, "en", "action.showPassword") == "Show password"
    assert _copy(i18n_src, "en", "action.hidePassword") == "Hide password"
    assert _copy(i18n_src, "es", "action.showPassword") == "Mostrar contraseña"
    assert "fa-eye" in login_src


def test_login_has_visible_labels_and_focus_rings(login_src, i18n_src):
    assert re.search(r'htmlFor:\s*"login-email"', login_src)
    assert re.search(r'htmlFor:\s*"login-password"', login_src)
    assert re.search(r'id:\s*"login-email"', login_src)
    assert re.search(r'id:\s*"login-password"', login_src)
    assert "focus-visible:ring-2" in login_src
    assert _copy_in_every_language(i18n_src, "label.email")["es"] == "Email"
    assert _copy_in_every_language(i18n_src, "label.password")["es"] == "Contraseña"


def test_login_shows_an_inline_spinner_while_signing_in(login_src, i18n_src):
    assert "animate-spin" in login_src
    assert re.search(r'aria-busy', login_src)
    assert "t('action.signingIn')" in login_src
    assert _copy_in_every_language(i18n_src, "action.signIn") == {"es": "Iniciar sesión", "en": "Sign in"}


def test_login_is_a_two_panel_layout_that_collapses_to_one_column(login_src):
    assert "grid-cols-1" in login_src
    # Two columns from the large breakpoint on; the track sizes are explicit.
    assert re.search(r"lg:grid-cols-\[", login_src)


def test_login_uses_readable_type(login_src):
    tiny = re.findall(r"text-\[(?:8|9|10)px\]", login_src)
    assert not tiny, f"login still renders body text at 9-10px: {tiny}"


def test_login_keeps_the_premium_link_and_the_logo_asset(login_src, i18n_src):
    assert PRICING_URL in login_src
    assert 'target: "_blank"' in login_src
    assert 'rel: "noopener noreferrer"' in login_src
    assert "t('help.plans')" in login_src
    assert _copy_in_every_language(i18n_src, "help.plans") == {
        "es": "Planes PREMIUM",
        "en": "PREMIUM plans",
    }
    assert LOGO_PATH in login_src


def test_login_opens_the_setup_guide(login_src, i18n_src):
    assert "t('help.guide')" in login_src
    assert _copy_in_every_language(i18n_src, "help.guide") == {
        "es": "Guía completa",
        "en": "Full guide",
    }
    assert re.search(r"setGuideOpen\(true\)", login_src)
    assert "window.SetupGuide" in login_src
    assert re.search(r"setGuideOpen\(false\)", login_src)


def test_login_switches_language_without_leaving_the_screen(login_src, i18n_src):
    # One width per button keeps the rail from shifting when the language changes.
    assert re.search(r"className:\s*\"w-\d+ py-", login_src)
    assert "i18n.LANGUAGES.map" in login_src
    assert re.search(r'"aria-pressed":\s*language === code', login_src)
    assert _copy_in_every_language(i18n_src, "lang.label") == {"es": "Idioma", "en": "Language"}


def test_login_announces_itself_as_the_main_surface_not_a_modal(login_src):
    # It renders the whole screen, so there is nothing behind it to make inert.
    assert re.search(r'role:\s*"main"', login_src)
    assert "aria-modal" not in login_src


# --------------------------------------------------------------------------
# SetupGuide: the screen behaviour
# --------------------------------------------------------------------------

def test_setup_guide_is_published_as_a_window_global(guide_src):
    assert "window.SetupGuide = SetupGuide" in guide_src
    # Controlled by the login: it receives the language and its setter.
    assert re.search(
        r"const SetupGuide = \(\{ onClose, language: languageProp, onLanguageChange \}\)", guide_src
    )


def test_setup_guide_closes_on_escape(guide_src):
    assert re.search(r"key\s*===\s*'Escape'", guide_src)
    assert "onClose()" in guide_src


def test_setup_guide_offers_a_close_action_labelled_from_the_dictionary(guide_src, content_src):
    assert "onClick: () => onClose()" in guide_src
    assert "doc.closeLabel" in guide_src
    assert _copy_in_every_language(content_src, "closeLabel") == {"es": "Cerrar", "en": "Close"}


def test_setup_guide_labels_itself_with_a_unique_id(guide_src):
    # A fixed element id would let a second instance steal the dialog label.
    assert "React.useId()" in guide_src
    assert re.search(r'"aria-labelledby":\s*titleId', guide_src)
    assert re.search(r'id:\s*titleId', guide_src)


def test_setup_guide_traps_keyboard_focus(guide_src):
    assert re.search(r"key\s*===\s*'Tab'", guide_src)
    assert "preventDefault" in guide_src
    assert "getFocusable" in guide_src
    assert "panelRef" in guide_src
    assert re.search(r"""addEventListener\(\s*['"]keydown""", guide_src)
    assert re.search(r"""removeEventListener\(\s*['"]keydown""", guide_src)
    # Focus moves back inside the panel at both ends of the tab order.
    assert re.search(r"last\.focus\(\)", guide_src)
    assert re.search(r"first\.focus\(\)", guide_src)


def test_setup_guide_restores_focus_when_it_closes(guide_src):
    assert "previouslyFocused" in guide_src
    assert re.search(r"previouslyFocused\.focus\(\)", guide_src)


def test_setup_guide_switches_language_through_its_owner(guide_src, content_src):
    assert "onLanguageChange" in guide_src
    # Mounted without an owner it still repaints instead of only writing storage.
    assert re.search(r"setOwnLanguage\(next\)", guide_src)
    assert _copy_in_every_language(content_src, "languageLabel") == {
        "es": "Idioma",
        "en": "Language",
    }


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


def test_setup_guide_content_loads_before_the_component():
    text = _read_without_newline_translation(INDEX)
    assert "lib/loginI18n.js" in text
    assert "lib/setupGuideContent.js" in text
    assert text.index("lib/loginI18n.js") < text.index("lib/setupGuideContent.js")
    assert text.index("lib/setupGuideContent.js") < text.index("components/SetupGuide.js")


def test_page_defines_the_entrance_animation_the_components_use():
    text = _read_without_newline_translation(INDEX)
    assert "@keyframes ql-fade" in text


@pytest.mark.parametrize("var,default", BRIDGE_DEFAULTS)
def test_guide_documents_each_env_var_with_its_real_default(content_src, var, default):
    for language in LANGUAGES:
        row = re.search(
            r"\[\s*'%s',\s*'%s'" % (var, re.escape(default)), _language_block(content_src, language)
        )
        assert row, (
            f"{var} must be documented with the default the code uses ({default!r}) "
            f"in the {language} dictionary"
        )


def test_guide_documents_the_token_requirement(content_src):
    for language in LANGUAGES:
        block = _language_block(content_src, language)
        assert re.search(r"\[\s*'MT5_BRIDGE_TOKEN',\s*'\(unset\)'", block)
        assert "0.0.0.0" in block
        assert "127.0.0.1" in block
    assert re.search(r"obligatorio", content_src, re.IGNORECASE)
    assert re.search(r"mandatory", content_src, re.IGNORECASE)


def test_guide_keeps_the_verified_commands_and_endpoints(content_src):
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
        assert fragment in content_src, f"guide lost the verified fragment: {fragment}"


def test_guide_does_not_invent_a_bridge_health_route(content_src):
    # mt5_server.py exposes no /health route; the documented local probe is
    # /api/balance with the bridge token, which the bridge really serves.
    assert "8081/health" not in content_src


def test_guide_has_seven_numbered_steps_in_every_language(content_src):
    for language in LANGUAGES:
        numbers = [int(n) for n in re.findall(r"\{\s*n:\s*(\d+),", _language_block(content_src, language))]
        assert numbers == [1, 2, 3, 4, 5, 6, 7], f"{language} steps drifted: {numbers}"


def test_guide_points_at_the_accounts_section_for_crypto_keys(content_src):
    assert re.search(r"Cuentas", _language_block(content_src, "es"))
    assert re.search(r"Accounts", _language_block(content_src, "en"))
    assert content_src.count("API key") >= 2


# --------------------------------------------------------------------------
# SetupGuide: flat structure instead of illustrations
# --------------------------------------------------------------------------

def test_guide_renders_the_topology_as_flat_text_instead_of_svg(guide_src, content_src):
    # The illustrations carried English text baked into the image, so they could
    # not be translated. The data path is a list of translated nodes now.
    assert "<svg" not in guide_src
    assert "dangerouslySetInnerHTML" not in guide_src
    for language in LANGUAGES:
        block = _language_block(content_src, language)
        assert block.count("label:") == 4, f"{language} topology lost a node"


def test_guide_uses_no_external_or_binary_assets(guide_src, content_src):
    for src in (guide_src, content_src):
        assert "https://" not in src
        assert not re.search(r"<img\b", src)
        assert not re.search(r"\bsrc\s*:", src)
        assert not re.search(r"\.(?:png|jpe?g|gif|webp)\b", src)
        assert "url(http" not in src


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


@pytest.mark.parametrize(
    "path", [LOGIN, GUIDE, I18N, CONTENT, DOC], ids=["login", "guide", "i18n", "content", "doc"]
)
def test_committed_files_contain_no_secret_shaped_literal(path):
    text = _read(path)
    for pattern in SECRET_PATTERNS:
        match = re.search(pattern, text)
        assert not match, f"{path.name} contains a secret-shaped literal: {match.group(0)!r}"


def test_index_html_still_uses_crlf_line_endings():
    raw = INDEX.read_bytes()
    assert b"\r\n" in raw
    assert raw.count(b"\r\n") > 100
