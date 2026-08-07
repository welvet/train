import pytest
from dataclasses import dataclass

from train.core.event_bus import EventBus
from train.core.events.base import Event


@dataclass(frozen=True, slots=True)
class PingEvent(Event):
    message: str = ""


@dataclass(frozen=True, slots=True)
class PongEvent(Event):
    pass


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


async def test_publish_calls_subscriber(bus: EventBus) -> None:
    received: list[PingEvent] = []
    bus.subscribe(PingEvent, lambda e: _append(received, e))
    await bus.publish(PingEvent(message="hello"))
    assert len(received) == 1
    assert received[0].message == "hello"


async def test_subscribe_to_base_catches_all(bus: EventBus) -> None:
    received: list[Event] = []
    bus.subscribe(Event, lambda e: _append(received, e))
    await bus.publish(PingEvent(message="a"))
    await bus.publish(PongEvent())
    assert len(received) == 2
    assert isinstance(received[0], PingEvent)
    assert isinstance(received[1], PongEvent)


async def test_subscribe_to_specific_ignores_others(bus: EventBus) -> None:
    received: list[PingEvent] = []
    bus.subscribe(PingEvent, lambda e: _append(received, e))
    await bus.publish(PongEvent())
    assert len(received) == 0


async def test_multiple_subscribers(bus: EventBus) -> None:
    results: list[str] = []
    bus.subscribe(PingEvent, lambda e: _append_val(results, "a"))
    bus.subscribe(PingEvent, lambda e: _append_val(results, "b"))
    await bus.publish(PingEvent())
    assert sorted(results) == ["a", "b"]


async def test_handler_error_does_not_break_others(bus: EventBus) -> None:
    received: list[Event] = []

    async def bad_handler(event: PingEvent) -> None:
        raise RuntimeError("boom")

    bus.subscribe(PingEvent, bad_handler)
    bus.subscribe(PingEvent, lambda e: _append(received, e))
    await bus.publish(PingEvent())
    assert len(received) == 1


async def test_unsubscribe(bus: EventBus) -> None:
    received: list[Event] = []
    handler = lambda e: _append(received, e)
    bus.subscribe(PingEvent, handler)
    bus.unsubscribe(PingEvent, handler)
    await bus.publish(PingEvent())
    assert len(received) == 0


async def test_publish_no_subscribers(bus: EventBus) -> None:
    await bus.publish(PingEvent())


async def test_event_has_timestamp() -> None:
    event = PingEvent()
    assert event.timestamp > 0


async def _append(lst: list, event: Event) -> None:
    lst.append(event)


async def _append_val(lst: list[str], val: str) -> None:
    lst.append(val)
