from __future__ import annotations

import asyncio

import pytest

from train.core.event_bus import EventBus
from train.core.events.hub import DetectorChanged, SetSwitchPosition, SwitchPositionChanged
from train.core.events.train import SetTrainSpeed
from train.modules.automation import DIVERGE, STRAIGHT, AutomationContext
from train.scripts.pit_stop import (
    CRUISE_SPEED,
    HUB,
    PITSTOP_SWITCH,
    PitStopController,
    PitStopSignal,
    PitStopState,
)


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


def _auto_ack_switches(bus: EventBus) -> None:
    async def acknowledge(event: SetSwitchPosition) -> None:
        await bus.publish(
            SwitchPositionChanged(
                hub_name=event.hub_name,
                switch_name=event.switch_name,
                angle=event.angle,
                ok=True,
            )
        )

    bus.subscribe(SetSwitchPosition, acknowledge)


def _collect(bus: EventBus, event_type: type) -> list:
    events = []

    async def collect(event) -> None:
        events.append(event)

    bus.subscribe(event_type, collect)
    return events


@pytest.fixture
async def controller(bus: EventBus):
    _auto_ack_switches(bus)
    ctx = AutomationContext(bus)
    instance = PitStopController(ctx, entry_delay=60, dwell_time=60)
    await instance.start()
    yield instance, ctx
    await instance.stop()
    await ctx.cleanup()


async def test_startup_arms_pitstop_and_sets_s2_side(bus: EventBus) -> None:
    _auto_ack_switches(bus)
    switches = _collect(bus, SetSwitchPosition)
    ctx = AutomationContext(bus)
    controller = PitStopController(ctx)

    await controller.start()

    assert controller.state is PitStopState.PITSTOP_ARMED
    assert controller.should_pitstop is True
    assert [(event.hub_name, event.switch_name, event.angle) for event in switches] == [
        (HUB, PITSTOP_SWITCH, DIVERGE)
    ]

    await controller.stop()
    await ctx.cleanup()


async def test_pitstop_flow_is_driven_by_state_machine(
    bus: EventBus, controller
) -> None:
    instance, _ = controller
    speeds = _collect(bus, SetTrainSpeed)
    switches = _collect(bus, SetSwitchPosition)

    await instance.on_detector(
        DetectorChanged(hub_name=HUB, detector_name="D1", triggered=True)
    )
    assert instance.state is PitStopState.ENTERING_PITSTOP
    assert speeds == []

    await instance.handle(PitStopSignal.ENTRY_TIMER_ELAPSED)
    assert instance.state is PitStopState.PITSTOP_DWELL
    assert [event.speed for event in speeds] == [0]

    await instance.handle(PitStopSignal.DWELL_TIMER_ELAPSED)
    assert instance.state is PitStopState.COMING_FROM_PITSTOP
    assert [event.speed for event in speeds] == [0, CRUISE_SPEED]

    await instance.handle(PitStopSignal.D1_TRIGGERED)
    assert instance.state is PitStopState.NORMAL
    assert instance.should_pitstop is False
    assert [event.speed for event in speeds] == [0, CRUISE_SPEED, 0, CRUISE_SPEED]
    assert [(event.switch_name, event.angle) for event in switches] == [
        (PITSTOP_SWITCH, STRAIGHT)
    ]


async def test_d2_arms_next_pitstop_from_normal(bus: EventBus, controller) -> None:
    instance, _ = controller
    switches = _collect(bus, SetSwitchPosition)
    instance.state = PitStopState.NORMAL

    await instance.on_detector(
        DetectorChanged(hub_name=HUB, detector_name="D2", triggered=True)
    )

    assert instance.state is PitStopState.PITSTOP_ARMED
    assert instance.should_pitstop is True
    assert [(event.switch_name, event.angle) for event in switches] == [
        (PITSTOP_SWITCH, DIVERGE)
    ]


async def test_d1_passes_without_actions_in_normal_mode(
    bus: EventBus, controller
) -> None:
    instance, _ = controller
    speeds = _collect(bus, SetTrainSpeed)
    switches = _collect(bus, SetSwitchPosition)
    instance.state = PitStopState.NORMAL

    await instance.on_detector(
        DetectorChanged(hub_name=HUB, detector_name="D1", triggered=True)
    )

    assert instance.state is PitStopState.NORMAL
    assert speeds == []
    assert switches == []


async def test_irrelevant_detector_signals_do_not_change_state(controller) -> None:
    instance, _ = controller

    await instance.on_detector(
        DetectorChanged(hub_name=HUB, detector_name="D9", triggered=True)
    )

    assert instance.state is PitStopState.PITSTOP_ARMED


async def test_real_timers_reenter_the_signal_handler(bus: EventBus) -> None:
    _auto_ack_switches(bus)
    speeds = _collect(bus, SetTrainSpeed)
    ctx = AutomationContext(bus)
    controller = PitStopController(ctx, entry_delay=0.01, dwell_time=0.01)
    await controller.start()

    await controller.handle(PitStopSignal.D1_TRIGGERED)
    await asyncio.sleep(0.05)

    assert controller.state is PitStopState.COMING_FROM_PITSTOP
    assert [event.speed for event in speeds] == [0, CRUISE_SPEED]

    await controller.stop()
    await ctx.cleanup()
