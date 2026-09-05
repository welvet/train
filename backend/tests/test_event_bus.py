import asyncio
from dataclasses import dataclass

import pytest

from train.core.event_bus import CommandResourceNotFound, EventBus
from train.domain import (
    Event,
    SetTrainSpeed,
    SystemState,
    TrainConnected,
    TrainSpeedChanged,
)


@dataclass(frozen=True, slots=True)
class PingEvent(Event):
    message: str = ""


@dataclass(frozen=True, slots=True)
class PongEvent(Event):
    pass


@pytest.fixture
def bus() -> EventBus:
    return EventBus(SystemState.from_topology(train_hubs={"express": "express"}))


async def test_publish_calls_subscriber(bus: EventBus) -> None:
    received: list[PingEvent] = []
    bus.subscribe(PingEvent, lambda e: _append(received, e))
    await bus.publish(PingEvent(message="hello"))
    assert len(received) == 1
    assert received[0].message == "hello"


async def test_state_is_reduced_before_subscribers_run(bus: EventBus) -> None:
    observed: list[bool] = []

    async def observe(event: TrainConnected) -> None:
        observed.append(bus.state.lego_hubs[event.train_name].connected)

    bus.subscribe(TrainConnected, observe)

    await bus.publish(TrainConnected(train_name="express"))

    assert observed == [True]


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


async def test_dispatch_timeout_includes_waiting_for_resource_lock(
    bus: EventBus,
) -> None:
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    commands: list[int] = []

    async def acknowledge(event: SetTrainSpeed) -> None:
        commands.append(event.speed)
        if event.speed == 10:
            first_started.set()
            await release_first.wait()
        await bus.publish(TrainSpeedChanged(
            train_name=event.train_name,
            speed=event.speed,
            success=True,
            request_id=event.request_id,
        ))

    bus.subscribe(SetTrainSpeed, acknowledge)
    first = asyncio.create_task(bus.dispatch(
        SetTrainSpeed(train_name="express", speed=10), timeout=1.0
    ))
    await first_started.wait()

    with pytest.raises(TimeoutError):
        await bus.dispatch(
            SetTrainSpeed(train_name="express", speed=20), timeout=0.01
        )

    release_first.set()
    result = await first
    assert isinstance(result, TrainSpeedChanged)
    assert commands == [10]


async def test_dispatch_matches_response_identity_and_payload(
    bus: EventBus,
) -> None:
    async def acknowledge(event: SetTrainSpeed) -> None:
        await bus.publish(TrainSpeedChanged(
            train_name="other",
            speed=event.speed,
            success=True,
            request_id=event.request_id,
        ))
        await bus.publish(TrainSpeedChanged(
            train_name=event.train_name,
            speed=99,
            success=True,
            request_id=event.request_id,
        ))
        await bus.publish(TrainSpeedChanged(
            train_name=event.train_name,
            speed=event.speed,
            success=True,
            request_id=event.request_id,
        ))

    bus.subscribe(SetTrainSpeed, acknowledge)

    result = await bus.dispatch(
        SetTrainSpeed(train_name="express", speed=25), timeout=1.0
    )

    assert isinstance(result, TrainSpeedChanged)
    assert result.train_name == "express"
    assert result.speed == 25


async def test_dispatch_rejects_unknown_command_resource(bus: EventBus) -> None:
    with pytest.raises(CommandResourceNotFound, match="unknown train: missing"):
        await bus.dispatch(SetTrainSpeed(train_name="missing", speed=25))


async def _append(lst: list, event: Event) -> None:
    lst.append(event)


async def _append_val(lst: list[str], val: str) -> None:
    lst.append(val)
