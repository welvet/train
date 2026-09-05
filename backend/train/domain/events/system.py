from __future__ import annotations

from dataclasses import dataclass

from train.domain.events.base import Event


@dataclass(frozen=True, slots=True)
class SystemStarted(Event):
    pass


@dataclass(frozen=True, slots=True)
class SystemShutdown(Event):
    pass


@dataclass(frozen=True, slots=True)
class AutomationHalt(Event):
    pass


@dataclass(frozen=True, slots=True)
class AutomationResume(Event):
    pass
