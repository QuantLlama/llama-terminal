"""Authentication must be the default, not a per-call-site decision.

Marking routes as token-protected while one call kept a bare `fetch` cost three
separate breakages: the request 401'd and the renderer crashed spreading the
error body. The page therefore wraps the global fetch.
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "src/platform/web/lib/authFetch.js"

NODE_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.env.HELPER, 'utf8');

const calls = [];
const sandbox = {
  console,
  URL,
  Headers,
  location: { origin: 'https://llama.example' },
  fetch: (input, init) => {
    calls.push({ input: typeof input === 'string' ? input : input.url, init: init || {} });
    return Promise.resolve({ ok: true, status: 200, json: async () => [] });
  },
  supabase: {
    auth: {
      getSession: async () => ({ data: { session: { access_token: 'token-abc' } } }),
    },
  },
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(source, sandbox);

(async () => {
  await sandbox.fetch('/api/history?symbol=X');
  await sandbox.fetch('/api/symbols?platform=crypto');
  await sandbox.fetch('/robots.txt');
  await sandbox.fetch('/api/platform/version');
  await sandbox.fetch('https://other.example/api/thing');

  const auth = calls.map((c) => {
    const h = c.init.headers || {};
    return Boolean(h.Authorization || (h.get && h.get('Authorization')));
  });
  console.log(JSON.stringify({ inputs: calls.map((c) => c.input), auth }));
})().catch((e) => { console.error(e); process.exit(1); });
"""


def test_global_fetch_authenticates_api_calls_by_default():
    result = subprocess.run(
        ["node", "-e", NODE_HARNESS],
        env={"HELPER": str(HELPER), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    by_input = dict(zip(payload["inputs"], payload["auth"]))
    assert by_input["/api/history?symbol=X"] is True
    assert by_input["/api/symbols?platform=crypto"] is True
    assert by_input["/robots.txt"] is False
    assert by_input["/api/platform/version"] is False, "public routes must stay anonymous"
    assert by_input["https://other.example/api/thing"] is False, (
        "another origin must not receive this session token"
    )


def test_the_helper_is_installed_and_idempotent():
    source = HELPER.read_text()
    assert "__qlAuthWrapped" in source, "the wrapper must not double-wrap fetch"
    assert "installDefaultFetch()" in source
    html = (ROOT / "src/platform/web/index.html").read_text(encoding="utf-8")
    assert re.search(r'<script[^>]+src="[^"]*authFetch\.js', html), (
        "index.html must load the helper before the app"
    )
