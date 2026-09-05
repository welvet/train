from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from train.domain.events.base import Event
from train.domain.events.hub import SetSwitchPosition, SwitchPositionChanged
from train.domain.events.system import AutomationHalt, AutomationResume
from train.domain.events.train import SetTrainSpeed, TrainSpeedChanged
from train.domain.state import SystemState


ResourceKey = Callable[[Event], tuple[str, ...]]
ResponseMatch = Callable[[Event, Event], bool]
ResponseSuccess = Callable[[Event], bool]
MissingResource = Callable[[Event, SystemState], str | None]


@dataclass(frozen=True, slots=True)
class CommandSpec:
    command_type: type[Event]
    resource_key: ResourceKey
    missing_resource: MissingResource
    response_type: type[Event] | None = None
    response_matches: ResponseMatch | None = None
    response_succeeded: ResponseSuccess | None = None


COMMANDS = (
    CommandSpec(
        command_type=SetTrainSpeed,
        resource_key=lambda event: (
            "train",
            _set_train_speed(event).train_name,
        ),
        missing_resource=lambda event, state: _missing_train(
            _set_train_speed(event), state
        ),
        response_type=TrainSpeedChanged,
        response_matches=lambda command, response: (
            _train_speed_changed(response).request_id
            == _set_train_speed(command).request_id
            and _train_speed_changed(response).train_name
            == _set_train_speed(command).train_name
            and _train_speed_changed(response).speed
            == _set_train_speed(command).speed
        ),
        response_succeeded=lambda response: _train_speed_changed(response).success,
    ),
    CommandSpec(
        command_type=SetSwitchPosition,
        resource_key=lambda event: (
            "switch",
            _set_switch_position(event).hub_name,
            _set_switch_position(event).switch_name,
        ),
        missing_resource=lambda event, state: _missing_switch(
            _set_switch_position(event), state
        ),
        response_type=SwitchPositionChanged,
        response_matches=lambda command, response: (
            _switch_position_changed(response).request_id
            == _set_switch_position(command).request_id
            and _switch_position_changed(response).hub_name
            == _set_switch_position(command).hub_name
            and _switch_position_changed(response).switch_name
            == _set_switch_position(command).switch_name
        ),
        response_succeeded=lambda response: _switch_position_changed(response).ok,
    ),
    CommandSpec(
        command_type=AutomationHalt,
        resource_key=lambda event: ("automation",),
        missing_resource=lambda event, state: None,
    ),
    CommandSpec(
        command_type=AutomationResume,
        resource_key=lambda event: ("automation",),
        missing_resource=lambda event, state: None,
    ),
)

_COMMANDS_BY_TYPE = {spec.command_type: spec for spec in COMMANDS}


def command_spec(command: Event) -> CommandSpec | None:
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


def _set_train_speed(event: Event) -> SetTrainSpeed:
    return cast(SetTrainSpeed, event)


def _train_speed_changed(event: Event) -> TrainSpeedChanged:
    return cast(TrainSpeedChanged, event)


def _set_switch_position(event: Event) -> SetSwitchPosition:
    return cast(SetSwitchPosition, event)


def _switch_position_changed(event: Event) -> SwitchPositionChanged:
    return cast(SwitchPositionChanged, event)
