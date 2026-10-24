"""Public gateway/risk boundary tests; no venue, files, or worker threads."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.services.order_gateway import gateway as gateway_module
from src.services.order_gateway import risk_validator as risk_module
from src.services.order_gateway.models import (
    OrderRequest, OrderSide, OrderSource, OrderStatus, OrderType, RejectionReason,
)


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 1, 14, 12, tzinfo=tz)


@pytest.fixture
def gateway(monkeypatch):
    # Subclass construction isolates the production singleton without replacing
    # validation, recording, dispatch, or any public gateway method.
    connector = Mock()
    connector.connect.return_value = True
    connector.get_current_price.return_value = 100.0
    connector.get_order_size_rules.return_value = {
        "min_amount": 1.0, "step": 1.0, "contract_size": 0.01,
    }
    connector.place_order.return_value = SimpleNamespace(order=123)

    class IsolatedGateway(gateway_module.OrderGateway):
        def __new__(cls, *args, **kwargs):
            return object.__new__(cls)

        def _setup_logging(self):
            pass  # Never create the production log file.

        def _get_connector(self, platform, account_id=None):
            return connector

    clock = SimpleNamespace(time=lambda: 1768392000.0)
    monkeypatch.setattr(gateway_module, "time", clock)
    monkeypatch.setattr(risk_module, "time", clock)
    monkeypatch.setattr(risk_module, "datetime", FixedDateTime)
    mirror = Mock()
    monkeypatch.setattr(gateway_module, "replicate_to_nt8_background", mirror)
    instance = IsolatedGateway(platform="crypto")
    yield instance, connector, mirror
    instance.stop()
    instance._executor.shutdown(wait=True, cancel_futures=True)


def order(**changes):
    values = dict(symbol="BTCUSD", side=OrderSide.BUY, quantity=1.0,
                  platform="crypto", client_order_id="fixture-order", timestamp=1768392000.0)
    values.update(changes)
    return OrderRequest(**values)


def assert_rejected(gateway, request, reason, message):
    instance, connector, mirror = gateway
    before = instance.get_status()
    calls = connector.place_order.call_count
    mirror_calls = mirror.call_count
    response = instance.submit_order(request)
    assert response.success is False
    assert response.status == OrderStatus.REJECTED
    assert response.rejection_reason == reason
    assert response.error_message == message
    assert response.client_order_id == request.client_order_id
    assert response.filled_qty == 0
    assert connector.place_order.call_count == calls
    assert mirror.call_count == mirror_calls
    after = instance.get_status()
    assert after["risk_stats"] == before["risk_stats"]
    expected = dict(before["metrics"])
    expected["total_orders_received"] += 1
    expected["orders_rejected"] += 1
    assert after["metrics"] == expected
    assert after["queue_size"] == before["queue_size"] == 0
    assert after["is_running"] == before["is_running"] is False
    return response


@pytest.mark.parametrize("quantity", [0.0, -1.0])
def test_crypto_nonpositive_size_is_rejected_before_dispatch(gateway, quantity):
    assert_rejected(gateway, order(quantity=quantity),
                    RejectionReason.VALIDATION_INVALID_SIZE,
                    "Cantidad debe ser mayor a 0")


@pytest.mark.parametrize("source", [OrderSource.MANUAL, OrderSource.ALGO])
def test_daily_order_boundary_records_only_successes(gateway, source):
    instance, connector, _ = gateway
    instance.set_risk_limits({"max_orders_per_day": 2})
    for count in (1, 2):
        response = instance.submit_order(order(source=source))
        assert response.success is True
        assert response.status == OrderStatus.FILLED
        assert response.rejection_reason is None
        assert connector.place_order.call_count == count
        stats = instance.get_status()["risk_stats"]
        assert stats["daily_orders"] == count
        assert stats["daily_algo_orders"] == (count if source == OrderSource.ALGO else 0)
        assert stats["daily_manual_orders"] == (count if source == OrderSource.MANUAL else 0)
        assert stats["positions"] == {}
    assert_rejected(gateway, order(source=source), RejectionReason.RISK_MAX_ORDERS,
                    "Límite diario de órdenes alcanzado (2)")


def test_algo_daily_limit_does_not_block_manual_orders(gateway):
    instance, connector, _ = gateway
    instance.set_risk_limits({"algo_max_orders_per_day": 1})
    assert instance.submit_order(order(source=OrderSource.ALGO)).success
    assert_rejected(gateway, order(source=OrderSource.ALGO), RejectionReason.RISK_MAX_ORDERS,
                    "Límite diario de órdenes ALGO alcanzado (1)")
    assert instance.submit_order(order()).success
    assert connector.place_order.call_count == 2
    stats = instance.get_status()["risk_stats"]
    assert (stats["daily_orders"], stats["daily_algo_orders"], stats["daily_manual_orders"]) == (2, 1, 1)


@pytest.mark.parametrize("loss", [500.0, 501.0])
def test_daily_loss_at_or_beyond_limit_blocks_dispatch(gateway, loss):
    instance, _, _ = gateway
    instance.update_pnl(-loss)
    assert instance.get_status()["metrics"]["daily_pnl"] == -loss
    assert instance.get_status()["risk_stats"]["daily_pnl"] == -loss
    assert_rejected(gateway, order(), RejectionReason.RISK_MAX_DAILY_LOSS,
                    f"Límite de pérdida diaria alcanzado (${loss:.2f})")


@pytest.mark.parametrize("quantity,expected_size", [(0.02, 2.0), (0.001, 1.0)])
def test_accepted_crypto_size_is_normalized_and_dispatched_once(gateway, quantity, expected_size):
    instance, connector, mirror = gateway
    instance.update_pnl(-499.0)  # Loss below the threshold still permits trading.
    callbacks = Mock()
    instance.subscribe_to_orders(callbacks)
    response = instance.submit_order(order(quantity=quantity, sl=90, tp=110))
    assert response.success is True
    assert response.status == OrderStatus.FILLED
    assert response.rejection_reason is None
    assert response.error_message == ""
    assert (response.order_id, response.quantity, response.filled_qty) == ("123", expected_size, expected_size)
    connector.place_order.assert_called_once_with(
        symbol="BTCUSD", order_type="BUY", volume=expected_size, price=None, sl=90, tp=110, mode="MKT")
    callbacks.assert_called_once_with(response)
    mirror.assert_not_called()
    status = instance.get_status()
    assert status["risk_stats"]["daily_orders"] == 1
    assert status["risk_stats"]["daily_manual_orders"] == 1
    assert status["risk_stats"]["daily_algo_orders"] == 0
    assert status["risk_stats"]["daily_pnl"] == -499.0
    assert status["risk_stats"]["positions"] == {}
    metrics = status["metrics"]
    assert (metrics["total_orders_received"], metrics["orders_validated"],
            metrics["orders_executed"], metrics["manual_orders"]) == (1, 1, 1, 1)
    assert (metrics["orders_failed"], metrics["orders_rejected"], metrics["algo_orders"]) == (0, 0, 0)


def test_broker_failure_does_not_consume_risk_allowance(gateway):
    instance, connector, mirror = gateway
    connector.place_order.return_value = None
    before = instance.get_status()["risk_stats"]
    response = instance.submit_order(order())
    assert response.success is False
    assert response.status == OrderStatus.FAILED
    assert response.rejection_reason == RejectionReason.CONNECTOR_ERROR
    assert response.error_message == "Orden rechazada por el broker"
    assert connector.place_order.call_count == 1
    mirror.assert_not_called()
    assert instance.get_status()["risk_stats"] == before
    metrics = instance.get_status()["metrics"]
    assert (metrics["orders_failed"], metrics["orders_validated"], metrics["manual_orders"],
            metrics["total_orders_received"]) == (1, 1, 1, 1)
    assert metrics["orders_executed"] == metrics["orders_rejected"] == 0


@pytest.mark.parametrize("source,quantity,limit", [
    (OrderSource.MANUAL, 11, 10.0), (OrderSource.ALGO, 6, 5.0),
])
def test_oversize_order_never_dispatches(gateway, source, quantity, limit):
    assert_rejected(gateway, order(source=source, quantity=quantity),
                    RejectionReason.RISK_MAX_POSITION_SIZE,
                    f"Cantidad excede límite ({float(quantity)} > {limit})")


def test_price_deviation_rejects_before_dispatch(gateway):
    assert_rejected(gateway, order(order_type=OrderType.LIMIT, price=102),
                    RejectionReason.RISK_PRICE_DEVIATION,
                    "Desviación de precio muy alta (2.0% > 1.0%)")
