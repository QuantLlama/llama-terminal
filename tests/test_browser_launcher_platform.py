"""Platform behaviour of the packaged browser launcher.

No real browser, backend process or network call is started: every side effect is
a synthetic stub and the frozen executable path points at a temporary file.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

import browser_launcher


class Recorder:
    def __init__(self):
        self.spawned = []
        self.opened = []
        self.sleeps = []
        self.ready_calls = 0
        self.initially_ready = False
        self.ready = True

    def spawn(self, argv, **kwargs):
        self.spawned.append((list(argv), kwargs))
        return object()

    def open(self, url):
        self.opened.append(url)
        return True

    def sleep(self, seconds):
        self.sleeps.append(seconds)

    def is_ready(self, port=None, timeout=1):
        self.ready_calls += 1
        # The first probe answers "is it already up?"; later probes are the
        # readiness wait loop after a spawn.
        return self.initially_ready if self.ready_calls == 1 else self.ready


@pytest.fixture
def harness(tmp_path, monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(browser_launcher.subprocess, 'Popen', rec.spawn)
    monkeypatch.setattr(browser_launcher.webbrowser, 'open', rec.open)
    monkeypatch.setattr(browser_launcher.time, 'sleep', rec.sleep)
    monkeypatch.setattr(browser_launcher, 'is_backend_running', rec.is_ready)
    monkeypatch.setattr(browser_launcher, 'find_running_backend', lambda: None)
    monkeypatch.setattr(browser_launcher, 'get_free_port', lambda start_port=8050, max_port=8100: 8050)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'BrowserMode'))
    return rec, tmp_path


def _backend(tmp_path, name, executable=True):
    path = tmp_path / name
    path.write_bytes(b'synthetic backend bytes')
    if executable:
        path.chmod(0o755)
    return path


@pytest.mark.skipif(os.name == 'nt', reason='non-Windows resolution rules')
def test_non_windows_launches_bare_backend_without_windows_flags(harness):
    rec, tmp_path = harness
    backend = _backend(tmp_path, 'backend')
    rec.ready = True
    browser_launcher.main()
    assert len(rec.spawned) == 1
    argv, kwargs = rec.spawned[0]
    assert argv == [str(backend), '--port', '8050']
    assert kwargs['cwd'] == str(tmp_path)
    assert 'creationflags' not in kwargs
    assert backend.read_bytes() == b'synthetic backend bytes'
    assert rec.opened == ['http://127.0.0.1:8050']


@pytest.mark.skipif(os.name == 'nt', reason='non-Windows resolution rules')
def test_non_windows_ignores_a_windows_named_backend(harness):
    rec, tmp_path = harness
    _backend(tmp_path, 'backend.exe')
    browser_launcher.main()
    assert rec.spawned == []
    assert rec.opened == []


def test_windows_keeps_backend_exe_and_hidden_console_flags(harness, monkeypatch):
    rec, tmp_path = harness
    monkeypatch.setattr(browser_launcher.os, 'name', 'nt')
    monkeypatch.setattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000, raising=False)
    backend = _backend(tmp_path, 'backend.exe')
    browser_launcher.main()
    assert len(rec.spawned) == 1
    argv, kwargs = rec.spawned[0]
    assert argv == [str(backend), '--port', '8050']
    assert kwargs['cwd'] == str(tmp_path)
    assert kwargs['creationflags'] == 0x08000000


def test_missing_backend_never_opens_the_browser(harness):
    rec, _ = harness
    browser_launcher.main()
    assert rec.spawned == []
    assert rec.opened == []


@pytest.mark.skipif(os.name == 'nt', reason='POSIX permission rule')
def test_non_executable_backend_is_refused(harness):
    rec, tmp_path = harness
    _backend(tmp_path, 'backend', executable=False)
    browser_launcher.main()
    assert rec.spawned == []
    assert rec.opened == []


def test_already_running_backend_is_reused_without_spawning(harness):
    rec, _ = harness
    rec.initially_ready = True
    browser_launcher.main()
    assert rec.spawned == []
    assert rec.opened == ['http://127.0.0.1:8050']


def test_readiness_timeout_does_not_open_the_browser(harness):
    rec, tmp_path = harness
    _backend(tmp_path, 'backend.exe' if os.name == 'nt' else 'backend')
    rec.ready = False
    browser_launcher.main()
    assert len(rec.spawned) == 1
    assert len(rec.sleeps) == 30
    assert rec.opened == []


@pytest.mark.skipif(os.name == 'nt', reason='Windows registry is unavailable')
def test_non_windows_browser_launch_does_not_report_a_registry_error(monkeypatch, capsys):
    opened = []
    monkeypatch.setattr(browser_launcher.webbrowser, 'open', opened.append)
    browser_launcher.launch_browser()
    assert opened == [browser_launcher.API_URL]
    assert 'Error launching browser' not in capsys.readouterr().out
