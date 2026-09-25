from decimal import Decimal

import pytest

from investing_plz.indicators import simple_moving_average


def test_simple_moving_average_uses_latest_values() -> None:
    values = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("8")]

    assert simple_moving_average(values, 3) == Decimal("13") / Decimal("3")


def test_simple_moving_average_accepts_exact_window() -> None:
    assert simple_moving_average([Decimal("2"), Decimal("4")], 2) == Decimal("3")


def test_simple_moving_average_returns_none_when_values_are_insufficient() -> None:
    assert simple_moving_average([Decimal("2")], 2) is None


@pytest.mark.parametrize("window", [0, -1])
def test_simple_moving_average_rejects_invalid_window(window: int) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        simple_moving_average([Decimal("1")], window)

