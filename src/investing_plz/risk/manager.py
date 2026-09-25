from dataclasses import replace
from decimal import Decimal

from investing_plz.domain import OrderIntent, OrderSide
from investing_plz.domain.decimal import round_down_to_step
from investing_plz.risk.models import (
    RiskContext,
    RiskDecision,
    RiskLimits,
    RiskStatus,
)


class BasicRiskManager:
    """Apply deterministic long-only limits before an intent becomes an order."""

    def evaluate(
        self,
        intent: OrderIntent,
        context: RiskContext,
        limits: RiskLimits,
    ) -> RiskDecision:
        if intent.side is OrderSide.SELL:
            return RiskDecision(
                status=RiskStatus.APPROVED,
                original_intent=intent,
                approved_intent=intent,
                reason="sell reduces long exposure; buy limits do not apply",
            )

        original_amount = intent.quantity * context.current_price
        max_position_value = context.portfolio_value * limits.max_instrument_weight
        exposure_headroom = max_position_value - context.current_position_value
        cash_headroom = context.available_cash - limits.min_cash_reserve

        if exposure_headroom <= 0:
            return _rejected(intent, "instrument exposure is already at or above its limit")
        if cash_headroom <= 0:
            return _rejected(intent, "minimum cash reserve leaves no amount available to buy")

        allowed_amounts = {
            "maximum order amount": limits.max_order_amount,
            "maximum instrument weight": exposure_headroom,
            "minimum cash reserve": cash_headroom,
        }
        allowed_amount = min(original_amount, *allowed_amounts.values())
        allowed_quantity = round_down_to_step(
            allowed_amount / context.current_price,
            context.quantity_step,
        )
        if allowed_quantity == 0:
            return _rejected(intent, "allowed quantity is smaller than quantity_step")

        if allowed_quantity == intent.quantity:
            return RiskDecision(
                status=RiskStatus.APPROVED,
                original_intent=intent,
                approved_intent=intent,
                reason="intent is within all configured risk limits",
            )

        binding_limits = [
            name for name, amount in allowed_amounts.items() if amount < original_amount
        ]
        reason = (
            "quantity reduced by " + ", ".join(binding_limits)
            if binding_limits
            else "quantity rounded down to quantity_step"
        )
        return RiskDecision(
            status=RiskStatus.ADJUSTED,
            original_intent=intent,
            approved_intent=replace(intent, quantity=allowed_quantity),
            reason=reason,
        )


def _rejected(intent: OrderIntent, reason: str) -> RiskDecision:
    return RiskDecision(
        status=RiskStatus.REJECTED,
        original_intent=intent,
        approved_intent=None,
        reason=reason,
    )
