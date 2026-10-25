"""Two regressions the native review caught in the MT5 access work.

Both were introduced while making the cloud stop importing the Windows-only
package, and both would have shipped silently:

1. The startup probe freed its own connector *after* the live services had
   connected, so a restarted container reported ``connected`` over an MT5
   session that had just been torn down.
2. The backtest rates path stopped calling ``initialize()`` on a local MT5, so a
   Windows install that nothing else had initialised returned no candles.

These tests are static and unit level on purpose: ``fastapi`` is not installable
here, so the startup order is asserted from the source instead of by booting the
application.
"""
from pathlib import Path

import pytest

from src.live import mt5_access

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src" / "platform" / "api" / "main.py"


def test_startup_probes_the_broker_before_starting_the_live_services():
    """The probe frees its connector, so it has to run before the services connect.

    Order matters: ``_publish_live_connection_state`` calls ``connector.shutdown``
    when it succeeds. Running it after ``startup_services`` tears down the session
    startup just established.
    """
    source = MAIN.read_text(encoding="utf-8")
    probe = source.index('await _publish_live_connection_state("mt5")')
    startup = source.index('await startup_services(platform="mt5")')

    assert probe < startup, (
        "startup runs the state probe after startup_services; the probe shuts its "
        "connector down and would kill the live MT5 session"
    )


def test_rates_from_pos_initializes_the_local_terminal_first(monkeypatch):
    """A local MT5 needs initialize() before copy_rates_from_pos answers."""
    calls = []

    class FakeModule:
        def initialize(self):
            calls.append("initialize")
            return True

        def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
            calls.append("copy_rates_from_pos")
            return None

    monkeypatch.setattr(mt5_access, "bridge_enabled", lambda: False)
    monkeypatch.setattr(mt5_access, "local_module", lambda: FakeModule())

    mt5_access.rates_from_pos("MESZ26", "1m", 5)

    assert calls[:2] == ["initialize", "copy_rates_from_pos"], (
        f"the local path called MT5 in the wrong order: {calls}"
    )


def test_rates_from_pos_does_not_raise_when_initialize_fails(monkeypatch):
    """A failing initialize is a missing runtime, not an exception for the caller."""
    class ExplodingModule:
        def initialize(self):
            raise RuntimeError("terminal not available")

        def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
            raise AssertionError("copy_rates_from_pos must not run after a failed initialize")

    monkeypatch.setattr(mt5_access, "bridge_enabled", lambda: False)
    monkeypatch.setattr(mt5_access, "local_module", lambda: ExplodingModule())

    assert mt5_access.rates_from_pos("MESZ26", "1m", 5) is None
