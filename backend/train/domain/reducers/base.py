from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from train.domain.events.base import Event

if TYPE_CHECKING:
    from train.domain.state import SystemState


EventT = TypeVar("EventT", bound=Event)

Reducer = Callable[["SystemState", Event], bool]
TypedReducer = Callable[["SystemState", EventT], bool]


def adapt(
    event_type: type[EventT], reducer: TypedReducer[EventT]
) -> Reducer:
    def adapted(state: SystemState, event: Event) -> bool:
        if not isinstance(event, event_type):
            raise TypeError(
                f"{reducer.__name__} cannot reduce {type(event).__name__}"
            )
        return reducer(state, event)

    return adapted


def set_if_different(
    target: object, field_name: str, value: object
) -> bool:
    if getattr(target, field_name) == value:
        return False
    setattr(target, field_name, value)
    return True
