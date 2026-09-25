import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from investing_plz.adapters.upbit import UpbitMarketDataProvider
from investing_plz.application.collect import collect_bars
from investing_plz.domain import Instrument
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
