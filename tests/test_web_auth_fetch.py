"""Browser-side tenant auth contract.

Every per-user API route derives its tenant from a Supabase bearer token, so the
browser must send ``Authorization: Bearer <access_token>``. ``lib/authFetch.js``
is the single sanctioned helper that reads the current session from the client
``index.html`` already created and forwards the request.

The call-site half is asserted statically from the real sources: these are
browser modules, so no browser, bundler or npm install is involved. The helper
half is asserted behaviourally by evaluating the module in a ``vm`` context with
a stubbed ``window``, client, ``fetch``, storage and console, so both the with-
token and the no-session paths are proven without touching a network.
"""
import json
import os
import re
import shutil
import subprocess
import textwrap
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src/platform/web"
HELPER = WEB / "lib/authFetch.js"
INDEX = WEB / "index.html"

# Endpoint prefixes whose handlers depend on ``get_authenticated_user_id``.
PER_USER_PREFIXES = (
    "/api/config",
    "/api/workspace/",
    "/api/workspaces",
    "/api/algolab/state",
    "/api/algolab/chat",
)

# Every audited call site: file, HTTP method, endpoint literal, expected count.
EXPECTED_CALL_SITES = Counter({
    ("index.html", "POST", "/api/workspace/${name}"): 1,
    ("index.html", "GET", "/api/workspace/${name}"): 1,
    ("index.html", "POST", "/api/config"): 2,
    ("index.html", "GET", "/api/workspaces"): 1,
    ("index.html", "GET", "/api/config"): 1,
    ("OrderEntry_Professional.js", "POST", "/api/config"): 1,
    ("SettingsModal.js", "GET", "/api/config"): 1,
    ("SettingsModal.js", "POST", "/api/config"): 1,
    ("WorkspacesModal.js", "GET", "/api/workspaces"): 1,
    ("WorkspacesModal.js", "DELETE", "/api/workspace/${encodeURIComponent(name)}"): 1,
    ("AlgoLab.js", "GET", "/api/algolab/state"): 1,
    ("AlgoLab.js", "POST", "/api/algolab/state"): 1,
    ("AlgoLab.js", "GET", "/api/algolab/chat/history"): 1,
    ("AlgoLab.js", "DELETE", "/api/algolab/chat/history"): 1,
    ("AlgoLab.js", "POST", "/api/algolab/chat"): 2,
    # Accounts and trading routes became token-authenticated in this change.
    ("index.html", "GET", "/api/accounts"): 1,
    ("index.html", "GET", "/api/account?platform=${platformParam}"): 1,
    ("index.html", "GET", "/api/symbols?platform=${platform}"): 1,
    ("index.html", "GET", "/api/symbol_info?symbol=${encodeURIComponent(activeSymbol)}"): 1,
    ("index.html", "GET", "/api/timeframes?platform=${platform}"): 1,
    ("index.html", "GET", "/api/deals?platform=${platformParam}&days=9999"): 1,
    ("index.html", "GET", "/api/realtime_batch?symbols=${encodeURIComponent(mappedSymbols)}&platform=${platformType}"): 1,
    ("index.html", "POST", "/api/order"): 1,
    ("OrderEntry_Professional.js", "POST", "/api/accounts/${newAccountId}/connect?platform=${newPlatform}"): 1,
    ("OrderEntry_Professional.js", "POST", "/api/accounts/${selectedAccountId}/leverage?platform=crypto"): 1,
    ("SettingsModal.js", "GET", "/api/accounts"): 1,
    ("SettingsModal.js", "GET", "/api/accounts/brokers?type=${p}"): 1,
    ("SettingsModal.js", "GET", "/api/accounts/server-search?q=${encodeURIComponent(searchTerm)}"): 1,
    ("SettingsModal.js", "POST", "/api/accounts/${id}/master?platform=${platform}"): 1,
    ("SettingsModal.js", "POST", "/api/accounts/${id}/test?platform=${platform}"): 1,
    ("SettingsModal.js", "PATCH", "/api/accounts/${id}?platform=${platform}"): 1,
    ("SettingsModal.js", "DELETE", "/api/accounts/${id}?platform=${platform}"): 1,
    # One call passes the endpoint through a variable chosen with a ternary.
    ("SettingsModal.js", "GET", "<variable>"): 1,
})

SOURCES = {
    "index.html": WEB / "index.html",
    "OrderEntry_Professional.js": WEB / "components/OrderEntry_Professional.js",
    "SettingsModal.js": WEB / "components/SettingsModal.js",
    "WorkspacesModal.js": WEB / "components/WorkspacesModal.js",
    "AlgoLab.js": WEB / "components/AlgoLab.js",
}

# A bare ``fetch(`` that is not the tail of ``authFetch(`` and not a method call.
BARE_FETCH_RE = re.compile(r"(?<![A-Za-z0-9_$.])fetch\s*\(")
AUTH_FETCH_RE = re.compile(r"(?<![A-Za-z0-9_$])authFetch\s*\(")
FIRST_ARG_RE = re.compile(r"""\s*(['"`])(.*?)\1""", re.S)
METHOD_RE = re.compile(r"""method\s*:\s*['"]([A-Z]+)['"]""")
SCRIPT_TAG_RE = re.compile(r"<script[^>]*\bsrc=[\"']([^\"']+)[\"']", re.I)

PUBLIC_PATHS = ("/api/readiness", "/api/platform/version", "/robots.txt", "/sitemap.xml")


def _source(name):
    return SOURCES[name].read_text(encoding="utf-8")


def _call_arguments(source, open_paren):
    """Return the argument text of a call, honoring nesting and string literals."""
    depth = 0
    quote = None
    index = open_paren
    while index < len(source):
        char = source[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return source[open_paren + 1:index]
        index += 1
    raise AssertionError(f"unbalanced call at offset {open_paren}")


def _collect_calls(pattern, source):
    calls = []
    for match in pattern.finditer(source):
        arguments = _call_arguments(source, match.end() - 1)
        calls.append(arguments)
    return calls


def _endpoint_of(arguments):
    match = FIRST_ARG_RE.match(arguments)
    return match.group(2) if match else None


def test_helper_exposes_a_single_sanctioned_entry_point():
    source = HELPER.read_text(encoding="utf-8")
    assert "authFetch" in source
    assert "Bearer " in source
    # The token stays in memory: never persisted, never logged, never in a URL.
    for forbidden in ("localStorage", "sessionStorage", "console", "document.cookie"):
        assert forbidden not in source, f"{forbidden} must not appear in authFetch.js"


def test_helper_is_loaded_before_the_components_that_call_it():
    html = INDEX.read_text(encoding="utf-8")
    tags = [src for src in SCRIPT_TAG_RE.findall(html)]
    helper_tags = [tag for tag in tags if "authFetch.js" in tag]
    assert helper_tags, "index.html must load lib/authFetch.js"
    helper_position = next(i for i, src in enumerate(tags) if "authFetch.js" in src)
    component_positions = [i for i, src in enumerate(tags) if "/components/" in src]
    assert component_positions, "sanity: components are loaded from index.html"
    assert helper_position < min(component_positions)


def test_every_audited_call_site_routes_through_the_helper():
    found = Counter()
    for name in SOURCES:
        source = _source(name)
        for arguments in _collect_calls(AUTH_FETCH_RE, source):
            endpoint = _endpoint_of(arguments)
            if endpoint is None:
                # The endpoint may come from a local variable; require that the
                # same file assigns it from an accounts route.
                assert "/api/accounts" in source, (
                    f"{name}: authFetch with a variable endpoint but no accounts route"
                )
                endpoint = "<variable>"
            method_match = METHOD_RE.search(arguments)
            method = method_match.group(1) if method_match else "GET"
            found[(name, method, endpoint)] += 1
    assert found == EXPECTED_CALL_SITES


def test_no_audited_call_site_still_uses_bare_fetch():
    offenders = []
    for name in SOURCES:
        source = _source(name)
        for arguments in _collect_calls(BARE_FETCH_RE, source):
            endpoint = _endpoint_of(arguments)
            if not endpoint:
                continue
            if any(endpoint.startswith(prefix) for prefix in PER_USER_PREFIXES):
                offenders.append(f"{name}: fetch({endpoint})")
    assert offenders == [], "per-user routes must use authFetch: " + "; ".join(offenders)


def test_public_endpoints_are_not_wrapped_by_the_helper():
    html = INDEX.read_text(encoding="utf-8")
    for arguments in _collect_calls(AUTH_FETCH_RE, html):
        endpoint = _endpoint_of(arguments)
        assert not any(prefix in str(endpoint) for prefix in PUBLIC_PATHS), endpoint


NODE_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync(process.env.AUTH_FETCH_HELPER_PATH, 'utf8');
// Assembled at runtime so no secret-shaped literal is ever committed.
const TOKEN = ['test', 'access', 'token', 'value'].join('-');

function serializeHeaders(headers) {
  if (headers === undefined) return { kind: 'undefined' };
  if (headers === null) return { kind: 'null' };
  if (typeof Headers !== 'undefined' && headers instanceof Headers) {
    const out = {};
    headers.forEach((value, key) => { out[key] = value; });
    return { kind: 'Headers', values: out };
  }
  if (Array.isArray(headers)) return { kind: 'array', values: headers };
  return { kind: 'object', values: Object.assign({}, headers) };
}

function serializeOptions(options) {
  if (!options) return { kind: 'none' };
  const copy = {};
  for (const key of Object.keys(options)) {
    if (key === 'headers') copy.headers = serializeHeaders(options.headers);
    else if (key === 'signal') copy.signal = '<signal>';
    else copy[key] = options[key];
  }
  return copy;
}

async function run(name, clientMode, init, useHeadersInstance) {
  const sentinel = { ok: true, scenario: name };
  const calls = [];
  const writes = [];

  function storage(label) {
    return {
      getItem: () => { writes.push(['getItem', label]); return null; },
      setItem: (key, value) => { writes.push(['setItem', label, String(key), String(value)]); },
      removeItem: (key) => { writes.push(['removeItem', label, String(key)]); },
      clear: () => { writes.push(['clear', label]); },
    };
  }

  const recordingConsole = {};
  for (const level of ['log', 'info', 'warn', 'error', 'debug']) {
    recordingConsole[level] = (...args) => {
      writes.push(['console.' + level, args.map(String).join(' ')]);
    };
  }

  const windowObject = {
    fetch: (input, options) => {
      calls.push([input, options]);
      return Promise.resolve(sentinel);
    },
    localStorage: storage('localStorage'),
    sessionStorage: storage('sessionStorage'),
    location: { href: 'https://terminal.example/terminal', search: '', hash: '' },
    console: recordingConsole,
  };

  const session = {
    access_token: TOKEN,
    token_type: 'bearer',
    user: { id: 'user-uuid' },
  };
  if (clientMode === 'session') {
    windowObject.supabase = { auth: { getSession: () => Promise.resolve({ data: { session }, error: null }) } };
  } else if (clientMode === 'empty-session') {
    windowObject.supabase = { auth: { getSession: () => Promise.resolve({ data: { session: null }, error: null }) } };
  } else if (clientMode === 'get-session-rejects') {
    windowObject.supabase = { auth: { getSession: () => Promise.reject(new Error('no session available')) } };
  } else if (clientMode === 'auth-undefined') {
    windowObject.supabase = { auth: undefined };
  }

  const context = vm.createContext({ window: windowObject, Headers, console: recordingConsole });
  vm.runInContext(source, context, { filename: 'authFetch.js' });

  const fn = windowObject.authFetch;
  let effectiveInit = init;
  if (useHeadersInstance && init && init.headers) {
    effectiveInit = Object.assign({}, init, { headers: new Headers(init.headers) });
  }
  let error = null;
  let returnedSentinel = false;
  if (typeof fn === 'function') {
    try {
      const result = await fn('/api/config', effectiveInit);
      returnedSentinel = result === sentinel;
    } catch (thrown) {
      error = String((thrown && thrown.message) || thrown);
    }
  }

  return {
    scenario: name,
    helperType: typeof fn,
    error,
    returnedSentinel,
    callCount: calls.length,
    calls: calls.map((call) => ({ input: call[0], options: serializeOptions(call[1]) })),
    initAfter: serializeOptions(init),
    writes,
    tokenLeaked: JSON.stringify(writes).includes(TOKEN),
    url: windowObject.location.href,
  };
}

(async () => {
  const scenarios = [];
  scenarios.push(await run('with-session', 'session',
    { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: '{"platform":"mt5"}' },
    false));
  scenarios.push(await run('no-session', 'empty-session',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' },
    false));
  scenarios.push(await run('session-lookup-throws', 'get-session-rejects',
    { method: 'GET' },
    false));
  scenarios.push(await run('client-auth-missing', 'auth-undefined',
    { method: 'GET' },
    false));
  scenarios.push(await run('caller-token-preserved', 'session',
    { method: 'GET', headers: { Authorization: 'Bearer caller-owned' } },
    false));
  scenarios.push(await run('no-init', 'session', undefined, false));
  scenarios.push(await run('headers-instance', 'session',
    { method: 'POST', headers: { 'Content-Type': 'application/json' } },
    true));
  process.stdout.write(JSON.stringify(scenarios));
})();
"""


@pytest.fixture(scope="module")
def helper_scenarios():
    node = shutil.which("node")
    assert node, "node is required to evaluate the browser helper (used by the static CI lane too)"
    env = dict(os.environ, AUTH_FETCH_HELPER_PATH=str(HELPER))
    result = subprocess.run(
        [node, "-e", textwrap.dedent(NODE_HARNESS)],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    return {scenario["scenario"]: scenario for scenario in json.loads(result.stdout)}


def _authorization_header(options):
    headers = options.get("headers") or {}
    values = headers.get("values") or {}
    for key, value in values.items():
        if str(key).lower() == "authorization":
            return value
    return None


def test_helper_is_exported_to_the_page(helper_scenarios):
    assert HELPER.exists()
    assert all(item["helperType"] == "function" for item in helper_scenarios.values())


def test_helper_adds_the_bearer_header_when_a_session_exists(helper_scenarios):
    scenario = helper_scenarios["with-session"]
    assert scenario["error"] is None
    assert scenario["returnedSentinel"] is True
    assert scenario["callCount"] == 1
    call = scenario["calls"][0]
    assert call["input"] == "/api/config"
    assert _authorization_header(call["options"]) == "Bearer test-access-token-value"
    # Every existing fetch option survives untouched.
    assert call["options"]["method"] == "POST"
    assert call["options"]["body"] == '{"platform":"mt5"}'
    assert call["options"]["credentials"] == "same-origin"
    assert call["options"]["headers"]["values"]["Content-Type"] == "application/json"
    # The caller's own init object is not mutated.
    assert _authorization_header(scenario["initAfter"]) is None


def test_helper_keeps_the_request_going_without_a_session(helper_scenarios):
    scenario = helper_scenarios["no-session"]
    assert scenario["error"] is None
    assert scenario["returnedSentinel"] is True
    assert scenario["callCount"] == 1
    assert _authorization_header(scenario["calls"][0]["options"]) is None
    assert scenario["calls"][0]["options"]["method"] == "POST"


def test_helper_does_not_throw_when_the_session_lookup_fails(helper_scenarios):
    scenario = helper_scenarios["session-lookup-throws"]
    assert scenario["error"] is None
    assert scenario["returnedSentinel"] is True
    assert scenario["callCount"] == 1
    assert _authorization_header(scenario["calls"][0]["options"]) is None


def test_helper_does_not_throw_when_the_client_is_unusable(helper_scenarios):
    scenario = helper_scenarios["client-auth-missing"]
    assert scenario["error"] is None
    assert scenario["returnedSentinel"] is True
    assert scenario["callCount"] == 1
    assert _authorization_header(scenario["calls"][0]["options"]) is None


def test_helper_keeps_an_explicit_authorization_header(helper_scenarios):
    scenario = helper_scenarios["caller-token-preserved"]
    assert _authorization_header(scenario["calls"][0]["options"]) == "Bearer caller-owned"


def test_helper_adds_only_the_authorization_header_without_init(helper_scenarios):
    scenario = helper_scenarios["no-init"]
    options = scenario["calls"][0]["options"]
    assert _authorization_header(options) == "Bearer test-access-token-value"
    assert set(options["headers"]["values"]) == {"Authorization"}


def test_helper_accepts_a_headers_instance(helper_scenarios):
    scenario = helper_scenarios["headers-instance"]
    assert scenario["error"] is None
    options = scenario["calls"][0]["options"]
    assert options["headers"]["kind"] == "Headers"
    assert _authorization_header(options) == "Bearer test-access-token-value"
    assert options["headers"]["values"]["content-type"] == "application/json"


def test_helper_never_persists_logs_or_puts_the_token_in_the_url(helper_scenarios):
    for name, scenario in helper_scenarios.items():
        token_writes = [write for write in scenario["writes"] if "test-access-token-value" in json.dumps(write)]
        assert token_writes == [], f"{name} leaked the token: {token_writes}"
        assert scenario["url"] == "https://terminal.example/terminal"
        assert "test-access-token-value" not in str(scenario["calls"][0]["input"])


def test_every_transferred_session_is_hydrated_into_the_client():
    """A session used for API validation must reach the browser client.

    Per-user routes now require a bearer token that the shared helper reads from
    `supabase.auth.getSession()`. A boot path that validates the transferred
    session but never calls `setSession` leaves that window unable to
    authenticate, so every such branch must hydrate the client.
    """
    source = (ROOT / "src/platform/web/index.html").read_text()
    lines = source.splitlines()
    missing = []
    for index, line in enumerate(lines):
        if "sessionToValidate = ts;" not in line:
            continue
        window = "\n".join(lines[index:index + 12])
        if "setSession(ts)" not in window and "setSession(tsession" not in window:
            missing.append(index + 1)
    assert len([l for l in lines if "sessionToValidate = ts;" in l]) >= 2, (
        "expected both boot paths to consume a transferred session"
    )
    assert missing == [], (
        "transferred session validated without hydrating the client at line(s) "
        + ", ".join(str(n) for n in missing)
    )
