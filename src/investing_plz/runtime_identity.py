from uuid import uuid4


def new_paper_order_id() -> str:
    return _new_runtime_id("paper-order")


def new_paper_fill_id() -> str:
    return _new_runtime_id("paper-fill")


def new_paper_correlation_id() -> str:
    return _new_runtime_id("paper-correlation")


def _new_runtime_id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"
