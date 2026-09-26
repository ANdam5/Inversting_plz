import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar


_correlation_id: ContextVar[str | None] = ContextVar(
    "paper_correlation_id", default=None
)


@contextmanager
def correlation_context(correlation_id: str) -> Iterator[None]:
    if not isinstance(correlation_id, str) or not correlation_id.strip():
        raise ValueError("correlation_id must not be empty")
    token = _correlation_id.set(correlation_id)
    try:
        yield
    finally:
        _correlation_id.reset(token)


def log_event(logger: logging.Logger, event: str, **context: object) -> None:
    if not isinstance(event, str) or not event.strip():
        raise ValueError("event must not be empty")
    structured = {"event": event}
    correlation_id = _correlation_id.get()
    if correlation_id is not None:
        structured["correlation_id"] = correlation_id
    structured.update(
        (name, value) for name, value in context.items() if value is not None
    )
    try:
        logger.info(event, extra=structured)
    except Exception:
        # Observability must not change trading state or execution semantics.
        return
