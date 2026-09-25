from collections.abc import Sequence
from typing import Protocol

from investing_plz.domain import Bar
from investing_plz.strategy.signal import Signal


class Strategy(Protocol):
    @property
    def strategy_id(self) -> str: ...

    def generate_signal(self, bars: Sequence[Bar]) -> Signal: ...

