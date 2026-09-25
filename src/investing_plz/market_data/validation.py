from collections.abc import Sequence
from datetime import datetime, timedelta

from investing_plz.domain import Bar
from investing_plz.market_data.errors import MarketDataValidationError


def validate_bar_series(
    bars: Sequence[Bar],
    interval: str,
    *,
    previous_timestamp: datetime | None = None,
) -> None:
    if interval != "day":
        raise MarketDataValidationError(f"unsupported interval: {interval}")

    expected_step = timedelta(days=1)
    timestamps = [bar.timestamp for bar in bars]
    if len(timestamps) != len(set(timestamps)):
        raise MarketDataValidationError("duplicate candle timestamp")
    if timestamps != sorted(timestamps):
        raise MarketDataValidationError("candles must be in ascending timestamp order")

    if previous_timestamp is not None and timestamps:
        _require_expected_step(previous_timestamp, timestamps[0], expected_step)
    for earlier, later in zip(timestamps, timestamps[1:]):
        _require_expected_step(earlier, later, expected_step)


def _require_expected_step(
    earlier: datetime, later: datetime, expected_step: timedelta
) -> None:
    if later - earlier != expected_step:
        raise MarketDataValidationError(
            f"missing candle between {earlier.isoformat()} and {later.isoformat()}"
        )

