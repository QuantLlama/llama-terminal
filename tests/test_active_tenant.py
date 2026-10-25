"""Contract for the active trading tenant and the background consumers.

One engine process serves many authenticated users, but background loops (the
crypto account monitor, the market-data engine, the order gateway and the
NinjaTrader replicator) have no request context. They may therefore only act on
the tenant an actual action selected - choosing a master account or connecting an
account - and must skip their work, with a single log line, while nobody has
selected one. Falling back to ``default_user`` or to "the first row in the table"
would trade another user's account, so each consumer is proven here: it neither
raises nor touches an account while the holder is empty, and it uses exactly the
id the holder carries otherwise.

The holder half is exercised through its public functions. The consumer half is
exercised through the real functions: the NinjaTrader replicator is called
directly, the engine and gateway connector seams are reached on instances built
without their ``__init__`` side effects (no log directory, no config file), and
the crypto monitor loop is executed from its real source with a sleep hook that
stops it after the first iteration.
"""
import ast
import asyncio
import json
import logging
import os
import sys
import threading
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.services import active_tenant
from src.services import replication_service

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src/platform/api/main.py"

# One phrase, asserted everywhere: it is what an operator greps for when a
# service stays quiet because no trading tenant is selected.
SKIP_MESSAGE = "no active trading user"


# ── the holder ─────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def empty_holder():
    active_tenant.clear_active_user_id()
    yield
    active_tenant.clear_active_user_id()


def test_holder_is_empty_before_any_action():
    assert active_tenant.get_active_user_id() is None


def test_holder_remembers_the_user_that_selected_it():
    assert active_tenant.set_active_user_id("user-a") == "user-a"
    assert active_tenant.get_active_user_id() == "user-a"
    active_tenant.set_active_user_id("user-b")
    assert active_tenant.get_active_user_id() == "user-b"


@pytest.mark.parametrize("value", ["", "   ", None, 7])
def test_holder_refuses_a_tenant_that_is_not_a_verified_id(value):
    with pytest.raises(TypeError):
        active_tenant.set_active_user_id(value)
    assert active_tenant.get_active_user_id() is None


def test_holder_clears_when_the_trading_session_ends():
    active_tenant.set_active_user_id("user-a")
    active_tenant.clear_active_user_id()
    assert active_tenant.get_active_user_id() is None


def test_logging_out_one_user_keeps_another_users_active_tenant():
    active_tenant.set_active_user_id("user-a")
    active_tenant.clear_active_user_id("user-b")
    assert active_tenant.get_active_user_id() == "user-a"
    active_tenant.clear_active_user_id("user-a")
    assert active_tenant.get_active_user_id() is None


def test_skip_line_is_logged_once_per_consumer(caplog):
    logger = logging.getLogger("active-tenant-contract")
    with caplog.at_level(logging.WARNING, logger="active-tenant-contract"):
        active_tenant.note_missing_active_user("consumer-one", logger)
        active_tenant.note_missing_active_user("consumer-one", logger)

    assert caplog.text.count(SKIP_MESSAGE) == 1
    assert "consumer-one" in caplog.text


# ── consumers ──────────────────────────────────────────────────────


@pytest.fixture
def diag_lines(monkeypatch):
    """Capture the replicator's diagnostics instead of writing a file."""
    lines = []
    monkeypatch.setattr(replication_service, "log_diag", lines.append)
    return lines


def _stub_nt8_manager(monkeypatch, accounts, records):
    class Manager:
        def get_accounts(self, *, user_id):
            records.append(user_id)
            return accounts

    monkeypatch.setattr(
        "src.services.ninjatrader_manager.get_nt8_manager", lambda: Manager()
    )


def _stub_crypto_connectors(monkeypatch, connector_calls, connector):
    module = types.ModuleType("src.live.crypto_connector")
    module.get_connector = lambda account_id, *, user_id: (
        connector_calls.append((account_id, user_id)) or connector
    )
    monkeypatch.setitem(sys.modules, "src.live.crypto_connector", module)
    return module


def _stub_account_manager(monkeypatch, module_name, factory_name, calls, accounts):
    class Manager:
        def get_accounts(self, *, user_id):
            calls.append(user_id)
            return accounts

    monkeypatch.setattr(f"{module_name}.{factory_name}", lambda: Manager())


def test_nt8_replication_does_nothing_without_an_active_tenant(
    monkeypatch, diag_lines, caplog
):
    records = []
    _stub_nt8_manager(
        monkeypatch, [{"id": "n1", "mirror_trading": True}], records
    )

    with caplog.at_level(logging.WARNING):
        replication_service.replicate_to_nt8_sync("ES", "BUY", 1)

    assert records == [], "the replicator must not even look up the account manager"
    assert diag_lines == []
    assert SKIP_MESSAGE in caplog.text


def test_nt8_replication_uses_exactly_the_active_tenant(
    monkeypatch, diag_lines, tmp_path
):
    exchange_dir = tmp_path / "nt8-exchange"
    exchange_dir.mkdir()
    records = []
    _stub_nt8_manager(
        monkeypatch,
        [
            {"id": "n1", "name": "bridge", "mirror_trading": True,
             "exchange_dir": str(exchange_dir)},
            {"id": "n2", "name": "stopped", "mirror_trading": False,
             "exchange_dir": str(exchange_dir)},
        ],
        records,
    )

    active_tenant.set_active_user_id("user-b")
    replication_service.replicate_to_nt8_sync("ES", "BUY", 1)

    assert records == ["user-b"]
    commands = (exchange_dir / "commands.txt").read_text().splitlines()
    assert len(commands) == 1
    assert commands[0].startswith("BUY|ES|1")


def _crypto_engine():
    from src.services.market_data_engine.engine import MarketDataEngine

    engine = object.__new__(MarketDataEngine)
    engine._platform = "crypto"
    engine._connectors = {}
    engine._connector_lock = threading.Lock()
    return engine


def test_market_data_engine_skips_crypto_without_an_active_tenant(
    monkeypatch, caplog
):
    manager_calls, connector_calls = [], []
    _stub_account_manager(
        monkeypatch, "src.services.crypto_manager", "get_crypto_manager",
        manager_calls, [{"id": "c1", "is_master": True}],
    )
    _stub_crypto_connectors(monkeypatch, connector_calls, connector="connector")

    engine = _crypto_engine()
    with caplog.at_level(logging.WARNING):
        assert engine._get_connector("crypto") is None

    assert manager_calls == []
    assert connector_calls == []
    assert engine._connectors.get("crypto") is None
    assert SKIP_MESSAGE in caplog.text


def test_market_data_engine_uses_exactly_the_active_tenant(monkeypatch, caplog):
    manager_calls, connector_calls = [], []
    _stub_account_manager(
        monkeypatch, "src.services.crypto_manager", "get_crypto_manager",
        manager_calls, [{"id": "c1", "is_master": True}],
    )
    _stub_crypto_connectors(monkeypatch, connector_calls, connector="connector")

    engine = _crypto_engine()
    active_tenant.set_active_user_id("user-b")
    with caplog.at_level(logging.WARNING):
        assert engine._get_connector("crypto") == "connector"

    assert manager_calls == ["user-b"]
    assert connector_calls == [("c1", "user-b")]
    assert SKIP_MESSAGE not in caplog.text


def test_market_data_engine_skips_tradovate_without_an_active_tenant(
    monkeypatch, caplog
):
    manager_calls = []
    _stub_account_manager(
        monkeypatch, "src.services.tradovate_manager", "get_tradovate_manager",
        manager_calls, [],
    )

    engine = _crypto_engine()
    with caplog.at_level(logging.WARNING):
        assert engine._get_connector("tradovate") is None

    assert manager_calls == []
    assert SKIP_MESSAGE in caplog.text


def _gateway():
    from src.services.order_gateway.gateway import OrderGateway

    gateway = object.__new__(OrderGateway)
    gateway._platform = "crypto"
    gateway._connectors = {}
    gateway._connector_lock = threading.Lock()
    return gateway


def test_order_gateway_skips_crypto_without_an_active_tenant(monkeypatch, caplog):
    manager_calls, connector_calls = [], []
    _stub_account_manager(
        monkeypatch, "src.services.crypto_manager", "get_crypto_manager",
        manager_calls, [{"id": "c1"}],
    )
    _stub_crypto_connectors(monkeypatch, connector_calls, connector="connector")

    gateway = _gateway()
    with caplog.at_level(logging.WARNING):
        assert gateway._get_connector("crypto") is None

    assert manager_calls == []
    assert connector_calls == []
    assert SKIP_MESSAGE in caplog.text


def test_order_gateway_uses_exactly_the_active_tenant(monkeypatch, caplog):
    manager_calls, connector_calls = [], []
    _stub_account_manager(
        monkeypatch, "src.services.crypto_manager", "get_crypto_manager",
        manager_calls, [{"id": "c1"}],
    )
    _stub_crypto_connectors(monkeypatch, connector_calls, connector="connector")

    gateway = _gateway()
    active_tenant.set_active_user_id("user-b")
    with caplog.at_level(logging.WARNING):
        assert gateway._get_connector("crypto") == "connector"

    assert manager_calls == ["user-b"]
    assert connector_calls == [("c1", "user-b")]


# ── the crypto account monitor loop ────────────────────────────────


class _LoopStopped(Exception):
    """Raised by the sleep hook so one loop iteration is observable."""


def _monitor(status_file):
    source = MAIN.read_text()
    tree = ast.parse(source)
    node = next(
        (
            item for item in tree.body
            if isinstance(item, ast.AsyncFunctionDef)
            and item.name == "monitor_crypto_accounts"
        ),
        None,
    )
    assert node is not None, "monitor_crypto_accounts is missing from main.py"

    async def stop(_seconds):
        raise _LoopStopped

    namespace = {
        "os": os,
        "json": json,
        "asyncio": SimpleNamespace(sleep=stop, to_thread=asyncio.to_thread),
        "logger": logging.getLogger("crypto-monitor-contract"),
        "STATUS_FILE": str(status_file),
        "get_active_user_id": active_tenant.get_active_user_id,
        "note_missing_active_user": active_tenant.note_missing_active_user,
    }
    exec(
        compile(ast.Module(body=[node], type_ignores=[]), str(MAIN), "exec"),
        namespace,
    )
    return namespace["monitor_crypto_accounts"]


class FakeMonitorConnector:
    connected = True

    def __init__(self):
        self.balance_calls = 0

    def get_balance(self):
        self.balance_calls += 1
        return 1000.0

    def get_equity(self):
        return 1010.0

    def get_positions(self):
        return [{"symbol": "BTC/USDT", "margin": 10.0}]


def test_crypto_monitor_writes_no_account_state_without_an_active_tenant(
    monkeypatch, tmp_path, caplog
):
    status_file = tmp_path / "live_status.json"
    manager_calls, connector_calls = [], []
    _stub_account_manager(
        monkeypatch, "src.services.crypto_manager", "get_crypto_manager",
        manager_calls, [{"id": "c1", "is_master": True, "broker": "bybit"}],
    )
    connector = FakeMonitorConnector()
    _stub_crypto_connectors(monkeypatch, connector_calls, connector=connector)

    monitor = _monitor(status_file)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(_LoopStopped):
            asyncio.run(monitor())

    assert manager_calls == []
    assert connector_calls == []
    assert connector.balance_calls == 0
    assert not status_file.exists(), "no account may be reported to the UI"
    assert SKIP_MESSAGE in caplog.text


def test_crypto_monitor_reports_the_active_tenants_master_account(
    monkeypatch, tmp_path, caplog
):
    status_file = tmp_path / "live_status.json"
    manager_calls, connector_calls = [], []
    _stub_account_manager(
        monkeypatch, "src.services.crypto_manager", "get_crypto_manager",
        manager_calls,
        [
            {"id": "c0", "is_master": False, "broker": "bybit"},
            {"id": "c1", "is_master": True, "broker": "bybit",
             "name": "bybit-main"},
        ],
    )
    _stub_crypto_connectors(
        monkeypatch, connector_calls, connector=FakeMonitorConnector()
    )

    active_tenant.set_active_user_id("user-b")
    monitor = _monitor(status_file)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(_LoopStopped):
            asyncio.run(monitor())

    assert manager_calls == ["user-b"]
    assert connector_calls == [("c1", "user-b")]
    payload = json.loads(status_file.read_text())
    assert payload["account"]["login"] == "bybit-main"
    assert payload["account"]["balance"] == 1000.0
    assert SKIP_MESSAGE not in caplog.text
