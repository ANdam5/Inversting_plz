from dataclasses import dataclass
from datetime import datetime, timedelta

from investing_plz.application.paper_reconciliation import (
    PaperReconciliationResult,
)
from investing_plz.domain import Bar
from investing_plz.domain.time import require_utc


class ManualKillSwitch:
    """Small in-memory operator switch; disabled is the safe default."""

    def __init__(self, *, trading_enabled: bool = False) -> None:
        if not isinstance(trading_enabled, bool):
            raise TypeError("trading_enabled must be a bool")
        self._trading_enabled = trading_enabled

    @property
    def is_trading_enabled(self) -> bool:
        return self._trading_enabled

    def enable(self) -> None:
        self._trading_enabled = True

    def disable(self) -> None:
        self._trading_enabled = False


@dataclass(frozen=True, slots=True)
class PaperSafetyResult:
    issues: tuple[str, ...]

    @property
    def is_safe_to_trade(self) -> bool:
        return not self.issues


def evaluate_paper_safety(
    latest_closed_bar: Bar | None,
    *,
    now: datetime,
    max_data_delay: timedelta,
    kill_switch: ManualKillSwitch,
    reconciliation: PaperReconciliationResult,
) -> PaperSafetyResult:
    """Evaluate operator, runtime, and completed-candle freshness guards."""

    require_utc(now)
    if not isinstance(max_data_delay, timedelta):
        raise TypeError("max_data_delay must be a timedelta")
    if max_data_delay < timedelta(0):
        raise ValueError("max_data_delay must not be negative")
    if not isinstance(kill_switch, ManualKillSwitch):
        raise TypeError("kill_switch must be a ManualKillSwitch")
    if not isinstance(reconciliation, PaperReconciliationResult):
        raise TypeError("reconciliation must be a PaperReconciliationResult")

    issues: list[str] = []
    if not kill_switch.is_trading_enabled:
        issues.append("manual kill switch is disabled")
    issues.extend(
        f"reconciliation: {issue}" for issue in reconciliation.issues
    )
    if latest_closed_bar is None:
        issues.append("no closed market data")
        return PaperSafetyResult(tuple(issues))
    if not isinstance(latest_closed_bar, Bar):
        raise TypeError("latest_closed_bar must be a Bar or None")
    if latest_closed_bar.interval != "day":
        issues.append(
            f"unsupported freshness timeframe: {latest_closed_bar.interval}"
        )
        return PaperSafetyResult(tuple(issues))

    latest_completion = latest_closed_bar.timestamp + timedelta(days=1)
    if latest_completion > now:
        issues.append("latest Bar completion is in the future")
    else:
        next_expected_completion = latest_completion + timedelta(days=1)
        if now > next_expected_completion + max_data_delay:
            issues.append(
                "stale market data: next expected completion="
                f"{next_expected_completion.isoformat()} now={now.isoformat()}"
            )
    return PaperSafetyResult(tuple(issues))
