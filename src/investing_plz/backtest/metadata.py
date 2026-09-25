from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from investing_plz.backtest.models import BacktestConfig
from investing_plz.domain import Bar, Instrument
from investing_plz.domain.decimal import require_decimal
from investing_plz.domain.time import require_utc
from investing_plz.risk import RiskLimits
from investing_plz.strategy import (
    MovingAverageCrossoverParameters,
    MovingAverageCrossoverStrategy,
)


@dataclass(frozen=True, slots=True)
class BacktestRunMetadata:
    instrument: Instrument
    timeframe: str
    dataset_start: datetime
    dataset_end: datetime
    bar_count: int
    dataset_version: str
    strategy_id: str
    fast_window: int
    slow_window: int
    initial_cash: Decimal
    target_weight: Decimal
    quantity_step: Decimal
    min_trade_amount: Decimal
    max_order_amount: Decimal
    max_instrument_weight: Decimal
    min_cash_reserve: Decimal
    fee_rate: Decimal
    slippage_bps: Decimal
    code_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, Instrument):
            raise TypeError("instrument must be an Instrument")
        if not self.timeframe.strip():
            raise ValueError("timeframe must not be empty")
        require_utc(self.dataset_start)
        require_utc(self.dataset_end)
        if self.dataset_start > self.dataset_end:
            raise ValueError("dataset_start must not be later than dataset_end")
        if self.bar_count <= 0:
            raise ValueError("bar_count must be greater than zero")
        if not self.dataset_version.strip():
            raise ValueError("dataset_version must not be empty")
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty")
        if not self.code_version.strip():
            raise ValueError("code_version must not be empty")

        MovingAverageCrossoverParameters(self.fast_window, self.slow_window)
        risk_limits = RiskLimits(
            max_order_amount=self.max_order_amount,
            max_instrument_weight=self.max_instrument_weight,
            min_cash_reserve=self.min_cash_reserve,
        )
        config = BacktestConfig(
            initial_cash=self.initial_cash,
            target_weight=self.target_weight,
            quantity_step=self.quantity_step,
            min_trade_amount=self.min_trade_amount,
            fee_rate=self.fee_rate,
            slippage_bps=self.slippage_bps,
            risk_limits=risk_limits,
        )
        if config.initial_cash <= 0:
            raise ValueError("initial_cash must be greater than zero")

    def to_dict(self) -> dict[str, object]:
        return {
            "instrument": {
                "venue": self.instrument.venue,
                "symbol": self.instrument.symbol,
            },
            "timeframe": self.timeframe,
            "dataset_start": self.dataset_start.isoformat(),
            "dataset_end": self.dataset_end.isoformat(),
            "bar_count": self.bar_count,
            "dataset_version": self.dataset_version,
            "strategy_id": self.strategy_id,
            "fast_window": self.fast_window,
            "slow_window": self.slow_window,
            "initial_cash": str(self.initial_cash),
            "target_weight": str(self.target_weight),
            "quantity_step": str(self.quantity_step),
            "min_trade_amount": str(self.min_trade_amount),
            "max_order_amount": str(self.max_order_amount),
            "max_instrument_weight": str(self.max_instrument_weight),
            "min_cash_reserve": str(self.min_cash_reserve),
            "fee_rate": str(self.fee_rate),
            "slippage_bps": str(self.slippage_bps),
            "code_version": self.code_version,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "BacktestRunMetadata":
        instrument = payload.get("instrument")
        if not isinstance(instrument, dict):
            raise ValueError("instrument must be an object")
        return cls(
            instrument=Instrument(
                venue=str(instrument["venue"]),
                symbol=str(instrument["symbol"]),
            ),
            timeframe=str(payload["timeframe"]),
            dataset_start=datetime.fromisoformat(str(payload["dataset_start"])),
            dataset_end=datetime.fromisoformat(str(payload["dataset_end"])),
            bar_count=int(payload["bar_count"]),
            dataset_version=str(payload["dataset_version"]),
            strategy_id=str(payload["strategy_id"]),
            fast_window=int(payload["fast_window"]),
            slow_window=int(payload["slow_window"]),
            initial_cash=_decimal_from(payload, "initial_cash"),
            target_weight=_decimal_from(payload, "target_weight"),
            quantity_step=_decimal_from(payload, "quantity_step"),
            min_trade_amount=_decimal_from(payload, "min_trade_amount"),
            max_order_amount=_decimal_from(payload, "max_order_amount"),
            max_instrument_weight=_decimal_from(
                payload, "max_instrument_weight"
            ),
            min_cash_reserve=_decimal_from(payload, "min_cash_reserve"),
            fee_rate=_decimal_from(payload, "fee_rate"),
            slippage_bps=_decimal_from(payload, "slippage_bps"),
            code_version=str(payload["code_version"]),
        )


def create_backtest_run_metadata(
    bars: Sequence[Bar],
    strategy: MovingAverageCrossoverStrategy,
    config: BacktestConfig,
    *,
    code_version: str,
    dataset_version: str,
) -> BacktestRunMetadata:
    if not bars:
        raise ValueError("backtest metadata requires at least one bar")
    return BacktestRunMetadata(
        instrument=bars[0].instrument,
        timeframe=bars[0].interval,
        dataset_start=bars[0].timestamp,
        dataset_end=bars[-1].timestamp,
        bar_count=len(bars),
        dataset_version=dataset_version,
        strategy_id=strategy.strategy_id,
        fast_window=strategy.fast_window,
        slow_window=strategy.slow_window,
        initial_cash=config.initial_cash,
        target_weight=config.target_weight,
        quantity_step=config.quantity_step,
        min_trade_amount=config.min_trade_amount,
        max_order_amount=config.risk_limits.max_order_amount,
        max_instrument_weight=config.risk_limits.max_instrument_weight,
        min_cash_reserve=config.risk_limits.min_cash_reserve,
        fee_rate=config.fee_rate,
        slippage_bps=config.slippage_bps,
        code_version=code_version,
    )


def _decimal_from(payload: dict[str, object], name: str) -> Decimal:
    value = payload[name]
    if not isinstance(value, str):
        raise TypeError(f"serialized {name} must be a string")
    return Decimal(value)
