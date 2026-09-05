from __future__ import annotations

from typing import TYPE_CHECKING

from train.domain.events.system import (
    AutomationHalt,
    AutomationResume,
    SystemShutdown,
    SystemStarted,
)
from train.domain.reducers.base import set_if_different

if TYPE_CHECKING:
    from train.domain.state import SystemState


def reduce_system_started(state: SystemState, event: SystemStarted) -> bool:
    return set_if_different(state, "running", True)


def reduce_system_shutdown(
    state: SystemState, event: SystemShutdown
) -> bool:
    return set_if_different(state, "running", False)


def reduce_automation_halt(
    state: SystemState, event: AutomationHalt
) -> bool:
    return set_if_different(state.automation, "halted", True)


def reduce_automation_resume(
    state: SystemState, event: AutomationResume
) -> bool:
    return set_if_different(state.automation, "halted", False)
