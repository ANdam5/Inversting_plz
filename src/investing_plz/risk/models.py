from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from investing_plz.domain import OrderIntent
from investing_plz.domain.decimal import require_decimal
from investing_plz.execution import validate_fee_rate


@dataclass(frozen=True, slots=True)
class RiskContext:
    portfolio_value: Decimal
    available_cash: Decimal
    current_position_value: Decimal
    current_price: Decimal
    quantity_step: Decimal
    fee_rate: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        for name in (
            "portfolio_value",
            "available_cash",
            "current_position_value",
            "current_price",
            "quantity_step",
        ):
            require_decimal(getattr(self, name), name=name)
        if self.portfolio_value < 0:
            raise ValueError("portfolio_value must not be negative")
        if self.available_cash < 0:
            raise ValueError("available_cash must not be negative")
        if self.current_position_value < 0:
            raise ValueError("current_position_value must not be negative")
        if self.current_price <= 0:
            raise ValueError("current_price must be greater than zero")
        if self.quantity_step <= 0:
            raise ValueError("quantity_step must be greater than zero")
        validate_fee_rate(self.fee_rate)


@dataclass(frozen=True, slots=True)
class RiskLimits:
    max_order_amount: Decimal
    max_instrument_weight: Decimal
    min_cash_reserve: Decimal

    def __post_init__(self) -> None:
        for name in (
            "max_order_amount",
            "max_instrument_weight",
            "min_cash_reserve",
        ):
            require_decimal(getattr(self, name), name=name)
        if self.max_order_amount <= 0:
            raise ValueError("max_order_amount must be greater than zero")
        if not Decimal("0") < self.max_instrument_weight <= Decimal("1"):
            raise ValueError("max_instrument_weight must be greater than 0 and at most 1")
        if self.min_cash_reserve < 0:
            raise ValueError("min_cash_reserve must not be negative")


class RiskStatus(StrEnum):
    APPROVED = "approved"
    ADJUSTED = "adjusted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class RiskDecision:
    status: RiskStatus
    original_intent: OrderIntent
    approved_intent: OrderIntent | None
    reason: str
