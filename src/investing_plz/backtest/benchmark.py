from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from investing_plz.backtest.costs import apply_slippage, calculate_fee
from investing_plz.backtest.metrics import (
    calculate_cagr,
    calculate_max_drawdown,
    calculate_total_return,
)
from investing_plz.backtest.models import (
    BacktestConfig,
    BacktestPortfolio,
    EquityPoint,
    Fill,
)
from investing_plz.domain import Bar, OrderSide
from investing_plz.domain.decimal import require_decimal, round_down_to_step


@dataclass(frozen=True, slots=True)
class PassiveBenchmarkResult:
    initial_cash: Decimal
    allocation_weight: Decimal
    final_cash: Decimal
    final_position_quantity: Decimal
    final_position_market_value: Decimal
    final_portfolio_value: Decimal
    fills: tuple[Fill, ...]
    equity_curve: tuple[EquityPoint, ...]

    @property
    def total_return(self) -> Decimal:
        return calculate_total_return(self.initial_cash, self.final_portfolio_value)

    @property
    def maximum_drawdown(self) -> Decimal:
        return calculate_max_drawdown(
            tuple(point.portfolio_value for point in self.equity_curve)
        )

    @property
    def cagr(self) -> Decimal:
        return calculate_cagr(
            self.initial_cash,
            self.final_portfolio_value,
            self.equity_curve[0].timestamp,
            self.equity_curve[-1].timestamp,
        )


def run_passive_benchmark(
    bars: Sequence[Bar],
    config: BacktestConfig,
    allocation_weight: Decimal,
) -> PassiveBenchmarkResult:
    """Buy once at the first open, then hold cash and the position unchanged."""

    _validate_benchmark_inputs(bars, config, allocation_weight)
    first_bar = bars[0]
    fill_price = apply_slippage(
        first_bar.open,
        OrderSide.BUY,
        config.slippage_bps,
    )
    allocation_budget = config.initial_cash * allocation_weight
    per_unit_cost = fill_price * (Decimal("1") + config.fee_rate)
    quantity = round_down_to_step(
        allocation_budget / per_unit_cost,
        config.quantity_step,
    )

    portfolio = BacktestPortfolio(cash=config.initial_cash)
    fills: tuple[Fill, ...] = ()
    if quantity > 0:
        fee_amount = calculate_fee(quantity, fill_price, config.fee_rate)
        fill = Fill(
            instrument=first_bar.instrument,
            timestamp=first_bar.timestamp,
            side=OrderSide.BUY,
            quantity=quantity,
            fill_price=fill_price,
            strategy_id="passive_benchmark",
            fee_amount=fee_amount,
        )
        portfolio = portfolio.apply(fill)
        fills = (fill,)

    equity_curve = tuple(
        EquityPoint(
            timestamp=bar.timestamp,
            portfolio_value=(
                portfolio.cash + portfolio.position_quantity * bar.close
            ),
        )
        for bar in bars
    )
    final_market_value = portfolio.position_quantity * bars[-1].close
    return PassiveBenchmarkResult(
        initial_cash=config.initial_cash,
        allocation_weight=allocation_weight,
        final_cash=portfolio.cash,
        final_position_quantity=portfolio.position_quantity,
        final_position_market_value=final_market_value,
        final_portfolio_value=portfolio.cash + final_market_value,
        fills=fills,
        equity_curve=equity_curve,
    )


def _validate_benchmark_inputs(
    bars: Sequence[Bar],
    config: BacktestConfig,
    allocation_weight: Decimal,
) -> None:
    if not bars:
        raise ValueError("passive benchmark requires at least one closed bar")
    if config.initial_cash <= 0:
        raise ValueError("initial_cash must be greater than zero")
    allocation_weight = require_decimal(allocation_weight, name="allocation_weight")
    if not Decimal("0") < allocation_weight <= Decimal("1"):
        raise ValueError("allocation_weight must be greater than 0 and at most 1")
    instrument = bars[0].instrument
    interval = bars[0].interval
    if any(bar.instrument != instrument or bar.interval != interval for bar in bars):
        raise ValueError("all bars must have the same instrument and interval")
    timestamps = [bar.timestamp for bar in bars]
    if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
        raise ValueError("bars must have unique timestamps in ascending order")
