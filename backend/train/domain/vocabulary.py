from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from train.domain.events.base import Event
from train.domain.events.hub import SetSwitchPosition
from train.domain.events.system import AutomationHalt, AutomationResume
from train.domain.events.train import SetTrainSpeed


class InvalidPublicEvent(ValueError):
    pass


EventDecoder = Callable[[Mapping[str, object]], Event]
EventEncoder = Callable[[Event], dict[str, object]]


@dataclass(frozen=True, slots=True)
class PublicEventSpec:
    name: str
    event_type: type[Event]
    decode: EventDecoder
    encode: EventEncoder


PUBLIC_EVENTS = (
    PublicEventSpec(
        "set_train_speed",
        SetTrainSpeed,
        lambda data: SetTrainSpeed(
            train_name=_required_string(data, "train_id"),
            speed=_bounded_int(data, "speed", minimum=-100, maximum=100),
        ),
        lambda event: {
            "train_id": _set_train_speed(event).train_name,
            "speed": _set_train_speed(event).speed,
            "request_id": _set_train_speed(event).request_id,
        },
    ),
    PublicEventSpec(
        "set_switch_position",
        SetSwitchPosition,
        lambda data: SetSwitchPosition(
            hub_name=_required_string(data, "hub_id"),
            switch_name=_required_string(data, "switch_id"),
            target=_switch_target(data),
        ),
        lambda event: {
            "hub_id": _set_switch_position(event).hub_name,
            "switch_id": _set_switch_position(event).switch_name,
            "target": _set_switch_position(event).target,
            "request_id": _set_switch_position(event).request_id,
        },
    ),
    PublicEventSpec(
        "automation_halt",
        AutomationHalt,
        lambda data: AutomationHalt(),
        lambda event: {},
    ),
    PublicEventSpec(
        "automation_resume",
        AutomationResume,
        lambda data: AutomationResume(),
        lambda event: {},
    ),
)

_PUBLIC_EVENTS_BY_NAME = {spec.name: spec for spec in PUBLIC_EVENTS}
_PUBLIC_EVENTS_BY_TYPE = {spec.event_type: spec for spec in PUBLIC_EVENTS}


def decode_public_event(payload: object) -> Event:
    if not isinstance(payload, Mapping):
        raise InvalidPublicEvent("body must be an event object")
    event_name = payload.get("type")
    if not isinstance(event_name, str):
        raise InvalidPublicEvent("event type must be a string")
    spec = _PUBLIC_EVENTS_BY_NAME.get(event_name)
    if spec is None:
        raise InvalidPublicEvent(f"unsupported event type: {event_name}")
    data = payload.get("data", {})
    if not isinstance(data, Mapping):
        raise InvalidPublicEvent("event data must be an object")
    return spec.decode(data)


def encode_public_event(event: Event) -> dict[str, Any]:
    spec = _PUBLIC_EVENTS_BY_TYPE.get(type(event))
    if spec is None:
        raise InvalidPublicEvent(
            f"event is not part of the public vocabulary: {type(event).__name__}"
        )
    return {"type": spec.name, "data": spec.encode(event)}


def _required_string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidPublicEvent(f"{key} must be a non-empty string")
    return value.strip()


def _bounded_int(
    data: Mapping[str, object],
    key: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = data.get(key)
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not minimum <= value <= maximum
    ):
        raise InvalidPublicEvent(
            f"{key} must be an integer in {minimum}..{maximum}"
        )
    return value


def _switch_target(data: Mapping[str, object]) -> str | int:
    value = data.get("target")
    if isinstance(value, bool):
        raise InvalidPublicEvent(
            "target must be straight, diverge, or an angle in 0..180"
        )
    if isinstance(value, int) and 0 <= value <= 180:
        return value
    if isinstance(value, str):
        target = {"s": "straight", "d": "diverge"}.get(
            value.lower(), value.lower()
        )
        if target in {"straight", "diverge"}:
            return target
    raise InvalidPublicEvent(
        "target must be straight, diverge, or an angle in 0..180"
    )


def _set_train_speed(event: Event) -> SetTrainSpeed:
    return cast(SetTrainSpeed, event)


def _set_switch_position(event: Event) -> SetSwitchPosition:
    return cast(SetSwitchPosition, event)
