from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from investing_plz.domain import Instrument, OrderSide
from investing_plz.domain.decimal import require_decimal
from investing_plz.domain.time import require_utc
from investing_plz.risk import RiskLimits


@dataclass(frozen=True, slots=True)
class Fill:
    """A complete simulated execution at one historical bar's open price."""

    instrument: Instrument
    timestamp: datetime
    side: OrderSide
    quantity: Decimal
    fill_price: Decimal
    strategy_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, Instrument):
            raise TypeError("instrument must be an Instrument")
        require_utc(self.timestamp)
        if not isinstance(self.side, OrderSide):
            raise TypeError("side must be an OrderSide")
        require_decimal(self.quantity, name="quantity")
        require_decimal(self.fill_price, name="fill_price")
        if self.quantity <= 0:
            raise ValueError("quantity must be greater than zero")
        if self.fill_price <= 0:
            raise ValueError("fill_price must be greater than zero")
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty")


@dataclass(frozen=True, slots=True)
class BacktestPortfolio:
    """The cash and one long position needed by the M3-A backtest."""

    cash: Decimal
    position_quantity: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        require_decimal(self.cash, name="cash")
        require_decimal(self.position_quantity, name="position_quantity")
        if self.cash < 0:
            raise ValueError("cash must not be negative")
        if self.position_quantity < 0:
            raise ValueError("position_quantity must not be negative")

    def value_at(self, price: Decimal) -> Decimal:
        price = require_decimal(price, name="price")
        if price <= 0:
            raise ValueError("price must be greater than zero")
        return self.cash + self.position_quantity * price

    def apply(self, fill: Fill) -> "BacktestPortfolio":
        amount = fill.quantity * fill.fill_price
        if fill.side is OrderSide.BUY:
            if amount > self.cash:
                raise ValueError("BUY fill amount exceeds available cash")
            return BacktestPortfolio(
                cash=self.cash - amount,
                position_quantity=self.position_quantity + fill.quantity,
            )
        if fill.quantity > self.position_quantity:
            raise ValueError("SELL fill quantity exceeds the current position")
        return BacktestPortfolio(
            cash=self.cash + amount,
            position_quantity=self.position_quantity - fill.quantity,
        )


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    initial_cash: Decimal
    target_weight: Decimal
    quantity_step: Decimal
    risk_limits: RiskLimits

    def __post_init__(self) -> None:
        require_decimal(self.initial_cash, name="initial_cash")
        require_decimal(self.target_weight, name="target_weight")
        require_decimal(self.quantity_step, name="quantity_step")
        if self.initial_cash < 0:
            raise ValueError("initial_cash must not be negative")
        if not Decimal("0") <= self.target_weight <= Decimal("1"):
            raise ValueError("target_weight must be between 0 and 1")
        if self.quantity_step <= 0:
            raise ValueError("quantity_step must be greater than zero")
        if not isinstance(self.risk_limits, RiskLimits):
            raise TypeError("risk_limits must be RiskLimits")


@dataclass(frozen=True, slots=True)
class BacktestResult:
    initial_cash: Decimal
    final_cash: Decimal
    final_position_quantity: Decimal
    final_position_market_value: Decimal
    final_portfolio_value: Decimal
    signal_count: int
    bullish_signal_count: int
    bearish_signal_count: int
    intent_count: int
    approved_count: int
    adjusted_count: int
    rejected_count: int
    fills: tuple[Fill, ...]

    @property
    def fill_count(self) -> int:
        return len(self.fills)
