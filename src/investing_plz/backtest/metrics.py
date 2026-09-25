from collections.abc import Sequence
from decimal import Decimal

from investing_plz.domain.decimal import require_decimal


def calculate_total_return(
    initial_value: Decimal,
    final_value: Decimal,
) -> Decimal:
    """Return total return as a ratio, not a currency amount."""

    initial_value = require_decimal(initial_value, name="initial_value")
    final_value = require_decimal(final_value, name="final_value")
    if initial_value <= 0:
        raise ValueError("initial_value must be greater than zero")
    if final_value < 0:
        raise ValueError("final_value must not be negative")
    return final_value / initial_value - Decimal("1")


def calculate_max_drawdown(values: Sequence[Decimal]) -> Decimal:
    """Return the largest peak-to-trough drawdown as a negative ratio."""

    if not values:
        raise ValueError("equity curve must not be empty")
    checked = [require_decimal(value, name="portfolio_value") for value in values]
    if any(value < 0 for value in checked):
        raise ValueError("portfolio_value must not be negative")

    running_peak = checked[0]
    maximum_drawdown = Decimal("0")
    for value in checked:
        if value > running_peak:
            running_peak = value
        if running_peak == 0:
            continue
        drawdown = value / running_peak - Decimal("1")
        if drawdown < maximum_drawdown:
            maximum_drawdown = drawdown
    return maximum_drawdown
