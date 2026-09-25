from decimal import ROUND_DOWN, Decimal


def require_decimal(value: object, *, name: str) -> Decimal:
    """Require an exact Decimal for a financial value; floats are not accepted."""

    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal")
    return value


def round_down_to_step(quantity: Decimal, step: Decimal) -> Decimal:
    """Round a non-negative Decimal down to an explicit quantity step."""

    quantity = require_decimal(quantity, name="quantity")
    step = require_decimal(step, name="step")
    if quantity < 0:
        raise ValueError("quantity must not be negative")
    if step <= 0:
        raise ValueError("step must be greater than zero")
    units = (quantity / step).to_integral_value(rounding=ROUND_DOWN)
    return units * step
