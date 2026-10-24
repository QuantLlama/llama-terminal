"""Readiness contracts without importing broker-backed application startup."""
import importlib.util
from pathlib import Path
import subprocess
from unittest.mock import Mock, patch

import pytest
import requests
from contextlib import contextmanager
from test_api_route_composition import composed_client

ROOT = Path(__file__).resolve().parents[1]


def route_client(payload):
    return contextmanager(composed_client)(lambda: payload)


@pytest.mark.parametrize("ready,status", [(True, 200), (False, 503), ("true", 503), (None, 503)])
def test_actual_readiness_route_precedes_spa_and_preserves_liveness(ready, status):
    payload = {"ready_for_ui": ready, "services": {"market_data": "OFFLINE"},
               "mt5_status": "stopped", "timestamp": 123.0}
    with route_client(payload) as client:
        live = client.get("/health")
        assert live.status_code == 200
        assert live.json() == payload
        assert live.headers["content-type"] == "application/json"
        response = client.get("/api/health")
        assert response.status_code == status
        assert response.headers["content-type"] == "application/json"
        assert response.json() == payload


@pytest.fixture
def launcher():
    spec = importlib.util.spec_from_file_location("readiness_browser", ROOT / "browser_launcher.py")
    module = importlib.util.module_from_spec(spec)
    with patch("requests.get", side_effect=requests.ConnectionError):
        spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("status,body,expected", [
    (200, {"ready_for_ui": True}, True),
    (200, {"ready_for_ui": False}, False),
    (200, {"ready_for_ui": "true"}, False),
    (200, {}, False), (200, [], False),
    (503, {"ready_for_ui": True}, False),
    (200, ValueError("HTML or malformed JSON"), False),
])
def test_browser_probe_validates_json(launcher, monkeypatch, status, body, expected):
    response = Mock(status_code=status)
    if isinstance(body, Exception):
        response.json.side_effect = body
    else:
        response.json.return_value = body
    get = Mock(return_value=response)
    monkeypatch.setattr(launcher.requests, "get", get)
    assert launcher.is_backend_running(8053) is expected
    get.assert_called_once_with("http://127.0.0.1:8053/api/health", timeout=1)


@pytest.mark.parametrize("error", [requests.ConnectionError(), requests.Timeout()])
def test_browser_probe_errors_are_not_ready(launcher, monkeypatch, error):
    monkeypatch.setattr(launcher.requests, "get", Mock(side_effect=error))
    assert launcher.is_backend_running(8050) is False


def test_browser_discovery_requires_readiness(launcher, monkeypatch):
    html = Mock(status_code=200)
    html.json.side_effect = ValueError("HTML")
    ready = Mock(status_code=200)
    ready.json.return_value = {"ready_for_ui": True}
    monkeypatch.setattr(launcher.requests, "get", Mock(side_effect=[html, ready]))
    assert launcher.find_running_backend() == 8051


@pytest.mark.parametrize("eventually_ready", [True, False])
def test_browser_startup_never_opens_before_ready(launcher, monkeypatch, eventually_ready):
    monkeypatch.setattr(launcher, "find_running_backend", lambda: None)
    monkeypatch.setattr(launcher, "get_free_port", lambda *args: 8050)
    states = iter([False, False] + ([True] if eventually_ready else [False] * 30))
    monkeypatch.setattr(launcher, "is_backend_running", lambda *args: next(states, False))
    monkeypatch.setattr(launcher, "backend_executable", lambda current_dir: "backend")
    monkeypatch.setattr(launcher.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    spawn = Mock()
    monkeypatch.setattr(launcher.subprocess, "Popen", spawn)
    monkeypatch.setattr(launcher.time, "sleep", lambda seconds: None)
    opened = Mock()
    monkeypatch.setattr(launcher, "launch_browser", opened)
    launcher.main()
    spawn.assert_called_once()
    assert opened.call_count == int(eventually_ready)


def test_browser_existing_ready_backend_opens_without_spawning(launcher, monkeypatch):
    monkeypatch.setattr(launcher, "find_running_backend", lambda: 8054)
    monkeypatch.setattr(launcher, "is_backend_running", lambda: True)
    spawn = Mock()
    opened = Mock()
    monkeypatch.setattr(launcher.subprocess, "Popen", spawn)
    monkeypatch.setattr(launcher, "launch_browser", opened)
    launcher.main()
    spawn.assert_not_called()
    opened.assert_called_once_with()
    assert launcher.API_URL == "http://127.0.0.1:8054"


def test_node_public_probes_and_wait_loop():
    script = r"""
const assert = require('node:assert/strict');
const http = require('node:http');
const { probeReadiness, waitForReadiness } = require('./electron/health');
(async () => {
  let mode = 'ready';
  let calls = 0;
  const server = http.createServer((req, res) => {
    assert.equal(req.url, '/api/health');
    calls++;
    if (mode === 'timeout') return;
    if (mode === 'disconnect') return req.socket.destroy();
    res.statusCode = mode === 'status' ? 503 : 200;
    res.end(mode === 'html' ? '<html>SPA</html>' : mode === 'malformed' ? '{' :
      JSON.stringify(mode === 'array' ? [] : {ready_for_ui:
        mode === 'ready' || (mode === 'transition' && calls > 1) ? true :
        mode === 'string' ? 'true' : false}));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const url = `http://127.0.0.1:${server.address().port}/api/health`;
  try {
    assert.equal(await probeReadiness(url, 50), true);
    for (mode of ['html', 'malformed', 'array', 'string', 'nonready', 'status', 'disconnect', 'timeout']) {
      assert.equal(await probeReadiness(url, 50), false, mode);
    }
    mode = 'transition'; calls = 0;
    await waitForReadiness(url, 500, 5);
    assert.ok(calls > 1);
    mode = 'html';
    await assert.rejects(waitForReadiness(url, 60, 5), /readiness/i);
    mode = 'timeout';
    const start = Date.now();
    await assert.rejects(waitForReadiness(url, 60, 5), /readiness/i);
    assert.ok(Date.now() - start < 400);
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
  assert.equal(await probeReadiness(url, 50), false);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True,
                            text=True, timeout=5)
    assert result.returncode == 0, result.stdout + result.stderr


def test_electron_startup_uses_validated_wait_without_http200_fallback():
    source = (ROOT / "electron/main.js").read_text()
    assert "await waitForReadiness(" in source
    assert "waitOn(" not in source
    # A failed readiness wait must not open the SPA as if startup succeeded.
    failure = source.split("Backend failed to start or timeout:", 1)[1].split("app.on('window-all-closed'", 1)[0]
    assert "createWindow()" not in failure
