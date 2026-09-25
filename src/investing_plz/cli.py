import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from investing_plz.adapters.upbit import UpbitMarketDataProvider
from investing_plz.application.collect import collect_bars
from investing_plz.backtest import BacktestConfig, run_backtest
from investing_plz.domain import Instrument
from investing_plz.risk import RiskLimits
from investing_plz.strategy import MovingAverageCrossoverStrategy
from investing_plz.storage import SQLiteBarStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="investing_plz")
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect", help="collect one page of market bars")
    collect.add_argument("--venue", required=True, choices=["upbit"])
    collect.add_argument("--symbol", required=True)
    collect.add_argument("--timeframe", required=True, choices=["day"])
    collect.add_argument("--database", type=Path, default=Path("data/market.db"))
    collect.add_argument("--timeout", type=float, default=10.0)
    collect.add_argument("--pages", type=int, default=1)

    summary = commands.add_parser("summary", help="summarize a local bar dataset")
    summary.add_argument("--venue", required=True)
    summary.add_argument("--symbol", required=True)
    summary.add_argument("--timeframe", required=True, choices=["day"])
    summary.add_argument("--database", type=Path, default=Path("data/market.db"))

    signal = commands.add_parser("signal", help="evaluate a strategy signal")
    signal.add_argument("--venue", required=True)
    signal.add_argument("--symbol", required=True)
    signal.add_argument("--timeframe", required=True, choices=["day"])
    signal.add_argument("--database", type=Path, default=Path("data/market.db"))
    signal.add_argument("--fast", type=int, default=20)
    signal.add_argument("--slow", type=int, default=60)

    backtest = commands.add_parser("backtest", help="replay closed bars deterministically")
    backtest.add_argument("--venue", required=True)
    backtest.add_argument("--symbol", required=True)
    backtest.add_argument("--timeframe", required=True, choices=["day"])
    backtest.add_argument("--database", type=Path, default=Path("data/market.db"))
    backtest.add_argument("--fast", type=int, default=20)
    backtest.add_argument("--slow", type=int, default=60)
    backtest.add_argument("--initial-cash", type=Decimal, default=Decimal("10000000"))
    backtest.add_argument("--target-weight", type=Decimal, default=Decimal("0.10"))
    backtest.add_argument(
        "--quantity-step", type=Decimal, default=Decimal("0.00000001")
    )
    backtest.add_argument(
        "--max-order-amount", type=Decimal, default=Decimal("500000")
    )
    backtest.add_argument(
        "--max-instrument-weight", type=Decimal, default=Decimal("0.20")
    )
    backtest.add_argument(
        "--min-cash-reserve", type=Decimal, default=Decimal("1000000")
    )
    backtest.add_argument(
        "--min-trade-amount", type=Decimal, default=Decimal("0")
    )
    backtest.add_argument("--fee-rate", type=Decimal, default=Decimal("0"))
    backtest.add_argument("--slippage-bps", type=Decimal, default=Decimal("0"))
    backtest.add_argument(
        "--show-fills",
        action="store_true",
        help="print simulated fill details after the summary",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    instrument = Instrument(venue=args.venue, symbol=args.symbol)
    if args.command == "summary":
        summary = SQLiteBarStore(args.database).summarize(
            instrument,
            args.timeframe,
            now=_utc_now(),
        )
        for field in (
            "venue",
            "symbol",
            "timeframe",
            "row_count",
            "closed_bar_count",
            "earliest_timestamp",
            "latest_timestamp",
            "latest_closed_timestamp",
            "duplicate_count",
            "gap_count",
        ):
            value = getattr(summary, field)
            print(f"{field}={value.isoformat() if isinstance(value, datetime) else value}")
        return 0

    if args.command == "signal":
        store = SQLiteBarStore(args.database)
        bars = store.load_closed_bars(
            instrument,
            args.timeframe,
            now=_utc_now(),
        )
        strategy = MovingAverageCrossoverStrategy(
            fast_window=args.fast,
            slow_window=args.slow,
        )
        evaluation = strategy.evaluate(bars)
        latest = bars[-1]
        output = {
            "instrument": f"{instrument.venue}:{instrument.symbol}",
            "latest_closed_timestamp": latest.timestamp.isoformat(),
            "latest_close": latest.close,
            "fast_window": strategy.fast_window,
            "slow_window": strategy.slow_window,
            "previous_fast_ma": evaluation.previous_fast_ma,
            "previous_slow_ma": evaluation.previous_slow_ma,
            "current_fast_ma": evaluation.current_fast_ma,
            "current_slow_ma": evaluation.current_slow_ma,
            "latest_signal": evaluation.signal.signal_type.value,
        }
        for key, value in output.items():
            print(f"{key}={value}")
        return 0

    if args.command == "backtest":
        bars = SQLiteBarStore(args.database).load_closed_bars(
            instrument,
            args.timeframe,
            now=_utc_now(),
        )
        strategy = MovingAverageCrossoverStrategy(
            fast_window=args.fast,
            slow_window=args.slow,
        )
        result = run_backtest(
            bars,
            strategy,
            BacktestConfig(
                initial_cash=args.initial_cash,
                target_weight=args.target_weight,
                quantity_step=args.quantity_step,
                min_trade_amount=args.min_trade_amount,
                fee_rate=args.fee_rate,
                slippage_bps=args.slippage_bps,
                risk_limits=RiskLimits(
                    max_order_amount=args.max_order_amount,
                    max_instrument_weight=args.max_instrument_weight,
                    min_cash_reserve=args.min_cash_reserve,
                ),
            ),
        )
        output = {
            "instrument": f"{instrument.venue}:{instrument.symbol}",
            "dataset_start": bars[0].timestamp.isoformat(),
            "dataset_end": bars[-1].timestamp.isoformat(),
            "closed_bar_count": len(bars),
            "initial_cash": result.initial_cash,
            "fast_window": strategy.fast_window,
            "slow_window": strategy.slow_window,
            "target_weight": args.target_weight,
            "signal_count": result.signal_count,
            "bullish_signal_count": result.bullish_signal_count,
            "bearish_signal_count": result.bearish_signal_count,
            "intent_count": result.intent_count,
            "approved_count": result.approved_count,
            "adjusted_count": result.adjusted_count,
            "rejected_count": result.rejected_count,
            "fill_count": result.fill_count,
            "final_cash": result.final_cash,
            "final_position_quantity": result.final_position_quantity,
            "final_position_market_value": result.final_position_market_value,
            "final_portfolio_value": result.final_portfolio_value,
            "fee_rate": args.fee_rate,
            "slippage_bps": args.slippage_bps,
            "total_fees": result.total_fees,
        }
        for key, value in output.items():
            print(f"{key}={value}")
        if args.show_fills:
            print("fills:")
            for sequence, fill in enumerate(result.fills, start=1):
                amount = fill.quantity * fill.fill_price
                print(
                    f"{sequence}. timestamp={fill.timestamp.isoformat()} "
                    f"side={fill.side.value.upper()} quantity={fill.quantity} "
                    f"fill_price={fill.fill_price} amount={amount} "
                    f"fee={fill.fee_amount} "
                    f"strategy_id={fill.strategy_id}"
                )
        return 0

    provider = UpbitMarketDataProvider(timeout=args.timeout, max_pages=args.pages)
    result = collect_bars(
        provider,
        SQLiteBarStore(args.database),
        instrument,
        args.timeframe,
    )
    print(
        f"fetched={result.fetched} inserted={result.inserted} "
        f"total={result.total} database={args.database}"
    )
    return 0
