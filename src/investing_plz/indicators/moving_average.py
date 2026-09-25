from collections.abc import Sequence
from decimal import Decimal


def simple_moving_average(
    values: Sequence[Decimal], window: int
) -> Decimal | None:
    """Return the mean of the latest window values, or None when insufficient."""

    if window <= 0:
        raise ValueError("window must be greater than zero")
    if len(values) < window:
        return None
    return sum(values[-window:], start=Decimal("0")) / Decimal(window)

