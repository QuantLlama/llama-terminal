"""The delivered units must not bring the MT5 terminal back by themselves.

A terminal that starts at login, or that is restarted every ten seconds after the
operator closes it, is indistinguishable from a bug to the person using the
machine. The bridge boots the terminal on demand instead, so the units carry that
contract: the terminal unit never restarts itself, the bridge unit never pulls it
in, and the installer stops enabling it at login.
"""

import configparser
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
UNITS = ROOT / "deploy" / "local"
TERMINAL_UNIT = UNITS / "qllama-mt5-terminal.service"
BRIDGE_UNIT = UNITS / "qllama-mt5-bridge.service"
INSTALLER = ROOT / "scripts" / "install_bridge_runtime.sh"


def _unit(path):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.read_string(path.read_text(encoding="utf-8"))
    return parser


def test_terminal_unit_never_restarts_itself():
    service = _unit(TERMINAL_UNIT)["Service"]

    assert service.get("Restart", "no") == "no", (
        "a restart policy here reopens the terminal every time the operator closes it"
    )


def test_bridge_unit_does_not_pull_the_terminal_unit_in():
    bridge = _unit(BRIDGE_UNIT)["Unit"]

    for key in ("After", "Wants", "Requires"):
        value = bridge.get(key, "")
        assert "qllama-mt5-terminal.service" not in value, (
            f"{key} starts the terminal at login, before anybody uses the platform"
        )


def test_bridge_unit_still_restarts_itself():
    service = _unit(BRIDGE_UNIT)["Service"]

    assert service.get("Restart") == "always", (
        "the bridge carries no window and must survive until the platform needs it"
    )


def test_installer_ships_the_terminal_demand_module():
    script = INSTALLER.read_text(encoding="utf-8")

    assert "src/live/mt5_terminal_demand.py" in script, (
        "the installed bridge imports it, so a stale runtime copy would crash"
    )


def test_installer_disables_the_terminal_autostart():
    script = INSTALLER.read_text(encoding="utf-8")

    assert "disable qllama-mt5-terminal.service" in script, (
        "install must stop the terminal from coming back at the next login"
    )
    assert "stop qllama-mt5-terminal.service" not in script, (
        "stopping the unit would close a terminal the operator is using"
    )
