from typing import Protocol

from investing_plz.domain import OrderIntent
from investing_plz.risk.models import RiskContext, RiskDecision, RiskLimits


class RiskManager(Protocol):
    def evaluate(
        self,
        intent: OrderIntent,
        context: RiskContext,
        limits: RiskLimits,
    ) -> RiskDecision: ...

