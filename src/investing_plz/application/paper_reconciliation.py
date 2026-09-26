from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from investing_plz.broker import PaperBroker
from investing_plz.broker.paper_account import project_paper_account
from investing_plz.domain.time import require_utc
from investing_plz.storage.paper import PaperCursorScope, PaperRepository


@dataclass(frozen=True, slots=True)
class PaperReconciliationResult:
    issues: tuple[str, ...]

    @property
    def is_safe_to_trade(self) -> bool:
        return not self.issues


class PaperTradingNotReadyError(RuntimeError):
    pass


def reconcile_paper_runtime(
    broker: PaperBroker,
    repository: PaperRepository,
    *,
    cursor_scope: PaperCursorScope | None = None,
) -> PaperReconciliationResult:
    """Compare durable paper state with its current in-memory projection."""

    if not isinstance(broker, PaperBroker):
        raise TypeError("broker must be a PaperBroker")
    issues: list[str] = []
    try:
        repository_orders = repository.list_orders()
        repository_fills = repository.list_fills()
        decisions = repository.list_order_decisions()
    except (TypeError, ValueError) as error:
        return PaperReconciliationResult((f"repository state is invalid: {error}",))

    broker_orders = broker.list_orders()
    broker_fills = broker.list_fills()
    _compare_by_id(
        repository_orders,
        broker_orders,
        id_attribute="order_id",
        label="order",
        issues=issues,
    )
    _compare_by_id(
        repository_fills,
        broker_fills,
        id_attribute="fill_id",
        label="fill",
        issues=issues,
    )

    for order in repository_orders:
        if order.is_open:
            issues.append(f"unresolved PENDING order: {order.order_id}")

    repository_order_by_id = {
        order.order_id: order for order in repository_orders
    }
    seen_decisions = set()
    seen_decision_orders: set[str] = set()
    for decision in decisions:
        if decision.decision_key in seen_decisions:
            issues.append("duplicate durable decision identity")
        seen_decisions.add(decision.decision_key)
        if decision.order_id in seen_decision_orders:
            issues.append(
                f"order linked to multiple decisions: {decision.order_id}"
            )
        seen_decision_orders.add(decision.order_id)
        order = repository_order_by_id.get(decision.order_id)
        if order is None:
            issues.append(
                f"decision references missing order: {decision.order_id}"
            )
            continue
        scope = decision.decision_key.scope
        if order.instrument != scope.instrument or order.strategy_id != scope.strategy_id:
            issues.append(
                f"decision scope does not match order: {decision.order_id}"
            )
    for order_id in sorted(repository_order_by_id.keys() - seen_decision_orders):
        issues.append(f"order has no durable decision mapping: {order_id}")

    try:
        projection = project_paper_account(
            broker.initial_cash,
            repository_orders,
            repository_fills,
        )
    except (TypeError, ValueError) as error:
        issues.append(f"durable account projection is invalid: {error}")
    else:
        if projection.cash != broker.cash:
            issues.append(
                f"cash mismatch: repository={projection.cash} broker={broker.cash}"
            )
        expected_positions = dict(projection.positions)
        broker_positions = dict(broker.list_positions())
        if expected_positions != broker_positions:
            issues.append(
                "position mismatch: repository="
                f"{_format_positions(expected_positions)} broker="
                f"{_format_positions(broker_positions)}"
            )

    if cursor_scope is not None:
        if not isinstance(cursor_scope, PaperCursorScope):
            raise TypeError("cursor_scope must be a PaperCursorScope or None")
        try:
            timestamp = repository.get_last_processed_bar_timestamp(cursor_scope)
            if timestamp is not None:
                require_utc(timestamp)
        except (TypeError, ValueError) as error:
            issues.append(f"cursor state is invalid: {error}")

    return PaperReconciliationResult(tuple(issues))


ResultT = TypeVar("ResultT")


def run_when_paper_ready(
    readiness: PaperReconciliationResult,
    operation: Callable[[], ResultT],
) -> ResultT:
    """Run an explicitly composed paper operation only when reconciliation is safe."""

    if not isinstance(readiness, PaperReconciliationResult):
        raise TypeError("readiness must be a PaperReconciliationResult")
    if not readiness.is_safe_to_trade:
        raise PaperTradingNotReadyError("; ".join(readiness.issues))
    return operation()


def _compare_by_id(
    durable_values,
    runtime_values,
    *,
    id_attribute: str,
    label: str,
    issues: list[str],
) -> None:
    durable = {getattr(value, id_attribute): value for value in durable_values}
    runtime = {getattr(value, id_attribute): value for value in runtime_values}
    for value_id in sorted(runtime.keys() - durable.keys()):
        issues.append(f"broker-only {label}: {value_id}")
    for value_id in sorted(durable.keys() - runtime.keys()):
        issues.append(f"repository-only {label}: {value_id}")
    for value_id in sorted(durable.keys() & runtime.keys()):
        if durable[value_id] != runtime[value_id]:
            issues.append(f"{label} content mismatch: {value_id}")


def _format_positions(positions) -> str:
    return ",".join(
        f"{instrument.venue}:{instrument.symbol}={quantity}"
        for instrument, quantity in sorted(
            positions.items(), key=lambda item: (item[0].venue, item[0].symbol)
        )
    )
