from datetime import datetime, timezone
from decimal import Decimal

import pytest

from investing_plz.domain import Instrument, OrderIntent, OrderSide
from investing_plz.risk import (
    BasicRiskManager,
    RiskContext,
    RiskLimits,
    RiskManager,
    RiskStatus,
)


def intent(side: OrderSide = OrderSide.BUY, quantity: str = "0.01") -> OrderIntent:
    return OrderIntent(
        instrument=Instrument("upbit", "KRW-BTC"),
        timestamp=datetime(2026, 9, 25, tzinfo=timezone.utc),
        strategy_id="moving_average_crossover",
        side=side,
        quantity=Decimal(quantity),
    )


def context(**overrides: object) -> RiskContext:
    values: dict[str, object] = {
        "portfolio_value": Decimal("10000000"),
        "available_cash": Decimal("5000000"),
        "current_position_value": Decimal("0"),
        "current_price": Decimal("100000000"),
        "quantity_step": Decimal("0.00000001"),
    }
    values.update(overrides)
    return RiskContext(**values)


def limits(**overrides: object) -> RiskLimits:
    values: dict[str, object] = {
        "max_order_amount": Decimal("2000000"),
        "max_instrument_weight": Decimal("0.20"),
        "min_cash_reserve": Decimal("1000000"),
    }
    values.update(overrides)
    return RiskLimits(**values)


def evaluate(
    order_intent: OrderIntent | None = None,
    risk_context: RiskContext | None = None,
    risk_limits: RiskLimits | None = None,
):
    manager: RiskManager = BasicRiskManager()
    return manager.evaluate(
        order_intent or intent(),
        risk_context or context(),
        risk_limits or limits(),
    )


def test_buy_within_all_limits_is_approved() -> None:
    decision = evaluate()

    assert decision.status is RiskStatus.APPROVED
    assert decision.approved_intent is decision.original_intent


def test_max_order_amount_adjusts_quantity() -> None:
    decision = evaluate(risk_limits=limits(max_order_amount=Decimal("500000")))

    assert decision.status is RiskStatus.ADJUSTED
    assert decision.approved_intent is not None
    assert decision.approved_intent.quantity == Decimal("0.00500000")


def test_max_instrument_weight_adjusts_quantity() -> None:
    decision = evaluate(
        risk_context=context(current_position_value=Decimal("1600000"))
    )

    assert decision.status is RiskStatus.ADJUSTED
    assert decision.approved_intent is not None
    assert decision.approved_intent.quantity == Decimal("0.00400000")


def test_buy_is_rejected_when_exposure_is_already_at_limit() -> None:
    decision = evaluate(
        risk_context=context(current_position_value=Decimal("2000000"))
    )

    assert decision.status is RiskStatus.REJECTED
    assert decision.approved_intent is None


def test_minimum_cash_reserve_adjusts_quantity() -> None:
    decision = evaluate(risk_context=context(available_cash=Decimal("1300000")))

    assert decision.status is RiskStatus.ADJUSTED
    assert decision.approved_intent is not None
    assert decision.approved_intent.quantity == Decimal("0.00300000")


def test_minimum_cash_reserve_accounts_for_buy_fee() -> None:
    decision = evaluate(
        order_intent=intent(quantity="0.01"),
        risk_context=context(
            available_cash=Decimal("1100000"),
            fee_rate=Decimal("0.10"),
        ),
        risk_limits=limits(min_cash_reserve=Decimal("100000")),
    )

    assert decision.status is RiskStatus.ADJUSTED
    assert decision.approved_intent is not None
    assert decision.approved_intent.quantity == Decimal("0.00909090")


def test_most_conservative_of_multiple_limits_wins() -> None:
    decision = evaluate(
        risk_context=context(
            current_position_value=Decimal("1600000"),
            available_cash=Decimal("1700000"),
        ),
        risk_limits=limits(max_order_amount=Decimal("500000")),
    )

    assert decision.status is RiskStatus.ADJUSTED
    assert decision.approved_intent is not None
    assert decision.approved_intent.quantity == Decimal("0.00400000")


def test_quantity_below_step_is_rejected() -> None:
    decision = evaluate(
        risk_context=context(
            current_position_value=Decimal("1999950"),
            quantity_step=Decimal("0.000001"),
        )
    )

    assert decision.status is RiskStatus.REJECTED
    assert decision.approved_intent is None


def test_sell_is_not_blocked_by_buy_cash_or_exposure_limits() -> None:
    sell = intent(side=OrderSide.SELL)
    decision = evaluate(
        order_intent=sell,
        risk_context=context(
            available_cash=Decimal("0"),
            current_position_value=Decimal("3000000"),
        ),
    )

    assert decision.status is RiskStatus.APPROVED
    assert decision.approved_intent is sell


def test_same_risk_manager_works_for_stock_instrument() -> None:
    stock_intent = OrderIntent(
        instrument=Instrument("stock", "SPY"),
        timestamp=datetime(2026, 9, 25, tzinfo=timezone.utc),
        strategy_id="moving_average_crossover",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
    )
    stock_context = RiskContext(
        portfolio_value=Decimal("10000000"),
        available_cash=Decimal("5000000"),
        current_position_value=Decimal("0"),
        current_price=Decimal("500000"),
        quantity_step=Decimal("1"),
    )

    decision = evaluate(order_intent=stock_intent, risk_context=stock_context)

    assert decision.status is RiskStatus.APPROVED
    assert decision.approved_intent is stock_intent


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_order_amount": Decimal("0")},
        {"max_order_amount": Decimal("-1")},
        {"max_instrument_weight": Decimal("0")},
        {"max_instrument_weight": Decimal("1.01")},
        {"min_cash_reserve": Decimal("-1")},
    ],
)
def test_invalid_risk_limits_are_rejected(overrides: dict[str, Decimal]) -> None:
    with pytest.raises(ValueError):
        limits(**overrides)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_order_amount", 500000.0),
        ("max_instrument_weight", 0.2),
        ("min_cash_reserve", 1000000.0),
    ],
)
def test_float_risk_limits_are_rejected(field: str, value: float) -> None:
    with pytest.raises(TypeError, match="Decimal"):
        limits(**{field: value})


def test_float_risk_context_is_rejected() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        context(current_price=100000000.0)
