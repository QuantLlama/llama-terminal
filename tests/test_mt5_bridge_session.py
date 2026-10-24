"""Tests for the bridge's lazy MT5 session handling."""

from src.live.mt5_bridge_session import ensure_connected


class _Connector:
    def __init__(self, connected=False, result=True, raises=False):
        self.connected = connected
        self.result = result
        self.raises = raises
        self.calls = 0

    def connect(self):
        self.calls += 1
        if self.raises:
            raise RuntimeError("terminal gone")
        self.connected = self.result
        return self.result


def test_connected_session_is_left_alone():
    connector = _Connector(connected=True)

    assert ensure_connected(connector) is True
    assert connector.calls == 0


def test_disconnected_session_is_reconnected():
    connector = _Connector(connected=False, result=True)

    assert ensure_connected(connector) is True
    assert connector.calls == 1


def test_failed_reconnect_reports_false():
    connector = _Connector(connected=False, result=False)

    assert ensure_connected(connector) is False
    assert connector.calls == 1


def test_reconnect_exception_is_swallowed():
    connector = _Connector(connected=False, raises=True)

    assert ensure_connected(connector) is False
    assert connector.calls == 1


def test_missing_connector_is_not_an_error():
    assert ensure_connected(None) is False
