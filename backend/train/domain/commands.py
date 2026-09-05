from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from train.domain.events.base import Event
from train.domain.events.hub import SetSwitchPosition, SwitchPositionChanged
from train.domain.events.system import AutomationHalt, AutomationResume
from train.domain.events.train import SetTrainSpeed, TrainSpeedChanged
from train.domain.state import SystemState


CommandT = TypeVar("CommandT", bound=Event)
ResponseT = TypeVar("ResponseT", bound=Event)

ResourceKey = Callable[[CommandT], tuple[str, ...]]
ResponseMatch = Callable[[CommandT, ResponseT], bool]
ResponseSuccess = Callable[[ResponseT], bool]
MissingResource = Callable[[CommandT, SystemState], str | None]


@dataclass(frozen=True, slots=True)
class CommandSpec(Generic[CommandT, ResponseT]):
    command_type: type[CommandT]
    resource_key: ResourceKey[CommandT]
    missing_resource: MissingResource[CommandT]
    response_type: type[ResponseT] | None = None
    response_matches: ResponseMatch[CommandT, ResponseT] | None = None
    response_succeeded: ResponseSuccess[ResponseT] | None = None


COMMANDS: tuple[CommandSpec[Any, Any], ...] = (
    CommandSpec[SetTrainSpeed, TrainSpeedChanged](
        command_type=SetTrainSpeed,
        resource_key=lambda event: (
            "train",
            event.train_name,
        ),
        missing_resource=lambda event, state: _missing_train(event, state),
        response_type=TrainSpeedChanged,
        response_matches=lambda command, response: (
            response.request_id == command.request_id
            and response.train_name == command.train_name
            and response.speed == command.speed
        ),
        response_succeeded=lambda response: response.success,
    ),
    CommandSpec[SetSwitchPosition, SwitchPositionChanged](
        command_type=SetSwitchPosition,
        resource_key=lambda event: (
            "switch",
            event.hub_name,
            event.switch_name,
        ),
        missing_resource=lambda event, state: _missing_switch(event, state),
        response_type=SwitchPositionChanged,
        response_matches=lambda command, response: (
            response.request_id == command.request_id
            and response.hub_name == command.hub_name
            and response.switch_name == command.switch_name
        ),
        response_succeeded=lambda response: response.ok,
    ),
    CommandSpec[AutomationHalt, Event](
        command_type=AutomationHalt,
        resource_key=lambda event: ("automation",),
        missing_resource=lambda event, state: None,
    ),
    CommandSpec[AutomationResume, Event](
        command_type=AutomationResume,
        resource_key=lambda event: ("automation",),
        missing_resource=lambda event, state: None,
    ),
)

_COMMANDS_BY_TYPE = {spec.command_type: spec for spec in COMMANDS}


def command_spec(command: Event) -> CommandSpec[Any, Any] | None:
    return _COMMANDS_BY_TYPE.get(type(command))


def _missing_train(command: SetTrainSpeed, state: SystemState) -> str | None:
    if command.train_name not in state.trains:
        return f"unknown train: {command.train_name}"
    return None


def _missing_switch(
    command: SetSwitchPosition, state: SystemState
) -> str | None:
    hub = state.arduino_hubs.get(command.hub_name)
    if hub is None:
        return f"unknown Arduino hub: {command.hub_name}"
    if command.switch_name not in hub.switches:
        return f"unknown switch: {command.hub_name}/{command.switch_name}"
    return None
