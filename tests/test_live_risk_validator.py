"""Position risk uses caller-supplied snapshots, not implicit fill accounting."""
from datetime import datetime
from types import SimpleNamespace

import pytest

from src.services.order_gateway import risk_validator as risk_module
from src.services.order_gateway.models import (
    OrderRequest, OrderSide, OrderSource, RejectionReason, RiskLimits,
)


@pytest.fixture
def validator(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 1, 14, 12, tzinfo=tz)

    monkeypatch.setattr(risk_module, "datetime", FixedDateTime)
    monkeypatch.setattr(risk_module, "time", SimpleNamespace(time=lambda: 1768392000.0))
    return risk_module.RiskValidator()


@pytest.mark.parametrize("source,limit", [(OrderSource.MANUAL, 10.0), (OrderSource.ALGO, 5.0)])
@pytest.mark.parametrize("side,sign", [(OrderSide.BUY, 1), (OrderSide.SELL, -1)])
def test_position_boundary_and_rejection_preserve_public_snapshot(validator, source, limit, side, sign):
    validator.update_position("BTCUSD", sign * (limit - 1))
    before = validator.get_stats()
    at_limit = OrderRequest("BTCUSD", side, 1, source=source)
    accepted = validator.validate(at_limit)
    assert accepted.is_valid is True
    assert accepted.rejection_reason is None
    assert accepted.message == "Orden válida"
    assert validator.get_stats() == before
    rejected = validator.validate(OrderRequest("BTCUSD", side, 2, source=source))
    assert rejected.is_valid is False
    assert rejected.rejection_reason == RejectionReason.RISK_MAX_POSITION_SIZE
    assert rejected.message == f"Posición resultante excede límite ({limit + 1:.2f} > {limit})"
    assert validator.get_stats() == before


def test_recording_an_order_counts_it_without_rewriting_position_snapshot(validator):
    validator.update_position("BTCUSD", 3.0)
    request = OrderRequest("BTCUSD", OrderSide.SELL, 1, source=OrderSource.ALGO)
    assert validator.validate(request).is_valid
    before = validator.get_stats()
    validator.record_order(request)
    expected = dict(before, daily_orders=1, daily_algo_orders=1)
    assert validator.get_stats() == expected
    validator.update_position("BTCUSD", 2.0)
    expected["positions"] = {"BTCUSD": 2.0}
    assert validator.get_stats() == expected


def test_default_limits_and_round_trip_remain_compatible(validator):
    assert validator.get_limits().to_dict() == RiskLimits().to_dict()
    assert validator.get_limits().max_orders_per_day == 50
    assert validator.get_limits().algo_max_orders_per_day == 20
    assert validator.get_limits().max_daily_loss == 500.0
    assert validator.get_limits().max_position_size == 10.0
    assert validator.get_limits().algo_max_position_size == 5.0
    limits = RiskLimits(max_orders_per_day=3, allowed_symbols=["BTCUSD"])
    validator.set_limits(limits)
    assert validator.get_stats()["limits"] == limits.to_dict()
    assert validator.get_limits().to_dict() == limits.to_dict()
