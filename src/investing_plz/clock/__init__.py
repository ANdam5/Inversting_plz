"""Injectable UTC clocks for application orchestration."""

from investing_plz.clock.fixed import FixedClock
from investing_plz.clock.protocol import Clock
from investing_plz.clock.system import SystemClock

__all__ = ["Clock", "FixedClock", "SystemClock"]
