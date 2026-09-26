from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from investing_plz.broker.models import ExecutionFill
from investing_plz.domain import Instrument, Order
from investing_plz.domain.time import require_utc
from investing_plz.domain.decimal import require_decimal
from investing_plz.execution import validate_fee_rate, validate_slippage_bps
from investing_plz.risk import RiskLimits
from investing_plz.strategy import MovingAverageCrossoverParameters


class PaperSessionConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PaperCursorScope:
    """Stable identity for one paper decision cursor."""

    instrument: Instrument
    strategy_id: str
    timeframe: str

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, Instrument):
            raise TypeError("instrument must be an Instrument")
        if not isinstance(self.strategy_id, str) or not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty")
        if not isinstance(self.timeframe, str) or not self.timeframe.strip():
            raise ValueError("timeframe must not be empty")


@dataclass(frozen=True, slots=True)
class PaperDecisionKey:
    """Identity of one strategy decision for one completed market bar."""

    scope: PaperCursorScope
    closed_bar_timestamp: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.scope, PaperCursorScope):
            raise TypeError("scope must be a PaperCursorScope")
        require_utc(self.closed_bar_timestamp)


@dataclass(frozen=True, slots=True)
class PaperOrderDecision:
    decision_key: PaperDecisionKey
    order_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.decision_key, PaperDecisionKey):
            raise TypeError("decision_key must be a PaperDecisionKey")
        if not isinstance(self.order_id, str) or not self.order_id.strip():
            raise ValueError("order_id must not be empty")


@dataclass(frozen=True, slots=True)
class PaperSessionConfig:
    """Durable identity for one Paper DB; strategy_id identifies semantics."""
    instrument: Instrument
    strategy_id: str
    timeframe: str
    fast_window: int
    slow_window: int
    target_weight: Decimal
    quantity_step: Decimal
    min_trade_amount: Decimal
    initial_cash: Decimal
    max_order_amount: Decimal
    max_instrument_weight: Decimal
    min_cash_reserve: Decimal
    fee_rate: Decimal
    slippage_bps: Decimal

    def __post_init__(self) -> None:
        PaperCursorScope(self.instrument, self.strategy_id, self.timeframe)
        MovingAverageCrossoverParameters(self.fast_window, self.slow_window)
        for name in (
            "target_weight",
            "quantity_step",
            "min_trade_amount",
            "initial_cash",
            "max_order_amount",
            "max_instrument_weight",
            "min_cash_reserve",
            "fee_rate",
            "slippage_bps",
        ):
            require_decimal(getattr(self, name), name=name)
        if not Decimal("0") <= self.target_weight <= Decimal("1"):
            raise ValueError("target_weight must be between 0 and 1")
        if self.quantity_step <= 0:
            raise ValueError("quantity_step must be greater than zero")
        if self.min_trade_amount < 0:
            raise ValueError("min_trade_amount must not be negative")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be greater than zero")
        RiskLimits(
            self.max_order_amount,
            self.max_instrument_weight,
            self.min_cash_reserve,
        )
        validate_fee_rate(self.fee_rate)
        validate_slippage_bps(self.slippage_bps)
    @property
    def scope(self) -> PaperCursorScope:
        return PaperCursorScope(
            self.instrument, self.strategy_id, self.timeframe
        )


class PaperRepository(Protocol):
    """Persistence contract for paper session config and runtime records."""

    def initialize(self) -> None: ...

    def register_session_config(self, config: PaperSessionConfig) -> bool: ...

    def get_session_config(
        self, scope: PaperCursorScope
    ) -> PaperSessionConfig | None: ...

    def list_session_configs(self) -> tuple[PaperSessionConfig, ...]: ...

    def save_order(self, order: Order) -> None: ...

    def get_order(self, order_id: str) -> Order | None: ...

    def list_orders(self) -> tuple[Order, ...]: ...

    def list_open_orders(self) -> tuple[Order, ...]: ...

    def register_order_submission(
        self, decision_key: PaperDecisionKey, order: Order
    ) -> bool: ...

    def get_order_for_decision(
        self, decision_key: PaperDecisionKey
    ) -> Order | None: ...

    def find_open_order_for_scope(
        self, scope: PaperCursorScope
    ) -> Order | None: ...

    def list_order_decisions(self) -> tuple[PaperOrderDecision, ...]: ...

    def save_fill(self, fill: ExecutionFill) -> bool: ...

    def get_fill(self, fill_id: str) -> ExecutionFill | None: ...

    def list_fills(self) -> tuple[ExecutionFill, ...]: ...

    def save_execution(
        self, order: Order, fill: ExecutionFill | None
    ) -> None: ...

    def get_last_processed_bar_timestamp(
        self, scope: PaperCursorScope
    ) -> datetime | None: ...

    def save_last_processed_bar_timestamp(
        self, scope: PaperCursorScope, timestamp: datetime
    ) -> None: ...

    def list_cursor_scopes(self) -> tuple[PaperCursorScope, ...]: ...
