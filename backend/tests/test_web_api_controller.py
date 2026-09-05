import asyncio

import pytest

from train.core.event_bus import EventBus
from train.domain import (
    SetSwitchPosition,
    SetTrainSpeed,
    SwitchPositionChanged,
    TrainConnected,
    TrainDisconnected,
    TrainSpeedChanged,
)
from train.modules.web_api.controller import WebApiController


async def test_controller_tracks_events_only_while_started() -> None:
    bus = EventBus()
    controller = WebApiController(bus, response_timeout=0.1)
    controller.start()

    await bus.publish(TrainConnected(train_name="arctic_express", ble_address="AA:BB"))
    assert controller.get_train("arctic_express")["connected"] is True  # type: ignore[index]

    controller.stop()
    await bus.publish(TrainDisconnected(train_name="arctic_express"))

    assert controller.get_train("arctic_express")["connected"] is True  # type: ignore[index]


async def test_controller_correlates_train_response() -> None:
    bus = EventBus()
    controller = WebApiController(bus, response_timeout=0.1)

    async def respond(event: SetTrainSpeed) -> None:
        await bus.publish(TrainSpeedChanged(
            train_name=event.train_name,
            speed=event.speed,
            success=True,
            request_id=event.request_id,
        ))

    bus.subscribe(SetTrainSpeed, respond)

    result = await controller.set_train_speed("arctic_express", 60)

    assert result.train_name == "arctic_express"
    assert result.speed == 60
    assert result.success


async def test_controller_correlates_switch_response() -> None:
    bus = EventBus()
    controller = WebApiController(bus, response_timeout=0.1)

    async def respond(event: SetSwitchPosition) -> None:
        await bus.publish(SwitchPositionChanged(
            hub_name=event.hub_name,
            switch_name=event.switch_name,
            angle=100,
            ok=True,
            request_id=event.request_id,
        ))

    bus.subscribe(SetSwitchPosition, respond)

    result = await controller.set_switch_position("HUB_A", "S1", "diverge")

    assert result.hub_name == "HUB_A"
    assert result.switch_name == "S1"
    assert result.angle == 100
    assert result.ok


async def test_controller_ignores_another_producers_train_response() -> None:
    bus = EventBus()
    controller = WebApiController(bus, response_timeout=0.1)

    async def respond(event: SetTrainSpeed) -> None:
        await bus.publish(TrainSpeedChanged(
            train_name=event.train_name,
            speed=99,
            success=True,
            request_id="automation-request",
        ))
        await bus.publish(TrainSpeedChanged(
            train_name=event.train_name,
            speed=event.speed,
            success=True,
            request_id=event.request_id,
        ))

    bus.subscribe(SetTrainSpeed, respond)

    result = await controller.set_train_speed("arctic_express", 60)

    assert result.speed == 60


async def test_controller_timeout_covers_dispatch() -> None:
    bus = EventBus()
    controller = WebApiController(bus, response_timeout=0.01)
    cancelled = asyncio.Event()

    async def hang(event: SetTrainSpeed) -> None:
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()

    bus.subscribe(SetTrainSpeed, hang)

    with pytest.raises(asyncio.TimeoutError):
        await controller.set_train_speed("arctic_express", 60)

    assert cancelled.is_set()


async def test_controller_switch_timeout_covers_dispatch() -> None:
    bus = EventBus()
    controller = WebApiController(bus, response_timeout=0.01)
    cancelled = asyncio.Event()

    async def hang(event: SetSwitchPosition) -> None:
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()

    bus.subscribe(SetSwitchPosition, hang)

    with pytest.raises(asyncio.TimeoutError):
        await controller.set_switch_position("HUB_A", "S1", "straight")

    assert cancelled.is_set()
