"""Deterministic historical replay for the minimal backtest baseline."""

from investing_plz.backtest.benchmark import (
    PassiveBenchmarkResult,
    run_passive_benchmark,
)
from investing_plz.backtest.costs import apply_slippage, calculate_fee
from investing_plz.backtest.metrics import (
    calculate_cagr,
    calculate_max_drawdown,
    calculate_total_return,
)
from investing_plz.backtest.metadata import (
    BacktestRunMetadata,
    create_backtest_run_metadata,
)
from investing_plz.backtest.models import (
    BacktestConfig,
    BacktestPortfolio,
    BacktestResult,
    EquityPoint,
    Fill,
)
from investing_plz.backtest.runner import run_backtest
from investing_plz.backtest.trade_metrics import (
    TradeMetrics,
    calculate_trade_metrics,
    calculate_trade_return,
)
from investing_plz.backtest.trades import ClosedTrade, build_closed_trades

__all__ = [
    "BacktestConfig",
    "BacktestPortfolio",
    "BacktestResult",
    "BacktestRunMetadata",
    "ClosedTrade",
    "EquityPoint",
    "Fill",
    "PassiveBenchmarkResult",
    "TradeMetrics",
    "apply_slippage",
    "calculate_fee",
    "calculate_cagr",
    "calculate_max_drawdown",
    "calculate_trade_metrics",
    "calculate_trade_return",
    "calculate_total_return",
    "create_backtest_run_metadata",
    "run_backtest",
    "run_passive_benchmark",
    "build_closed_trades",
]
