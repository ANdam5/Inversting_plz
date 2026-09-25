import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from investing_plz.adapters.upbit import UpbitMarketDataProvider
from investing_plz.application.collect import collect_bars
from investing_plz.domain import Instrument
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
