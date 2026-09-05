from __future__ import annotations

import asyncio

import pytest

import train.automation as automation_api
import train.modules.automation as automation_module
from train.core.event_bus import EventBus
from train.domain import (
    SetSwitchPosition,
    SetTrainSpeed,
    SwitchPositionChanged,
    SystemState,
    SystemStarted,
    TagDetected,
    TrainConnected,
    TrainSpeedChanged,
)
from train.modules.automation import AutomationContext, AutomationModule


@pytest.fixture
def bus() -> EventBus:
    return EventBus(SystemState.from_topology(
        train_hubs={"t1": "t1"},
        arduino_hubs={
            "hub": {"switches": {"S1": {}}, "detectors": ()}
        },
    ))


@pytest.fixture
def ctx(bus: EventBus) -> AutomationContext:
    return AutomationContext(bus)


def test_public_automation_api_only_exports_context() -> None:
    assert automation_api.AutomationContext is AutomationContext
    assert automation_api.__all__ == ["AutomationContext"]
    assert not hasattr(automation_api, "TagDetected")


def _auto_ack_switches(bus: EventBus) -> None:
    async def _ack(event: SetSwitchPosition) -> None:
        angle = event.target if isinstance(event.target, int) else 0
        await bus.publish(SwitchPositionChanged(
            hub_name=event.hub_name, switch_name=event.switch_name,
            angle=angle, ok=True, request_id=event.request_id,
        ))

    bus.subscribe(SetSwitchPosition, _ack)


def _collect(bus: EventBus, event_type):
    collected = []

    async def handler(e):
        collected.append(e)

    bus.subscribe(event_type, handler)
    return collected


# --- AutomationContext unit tests ---


async def test_set_speed_publishes(bus: EventBus, ctx: AutomationContext) -> None:
    async def acknowledge(event: SetTrainSpeed) -> None:
        await bus.publish(TrainSpeedChanged(
            train_name=event.train_name,
            speed=event.speed,
            success=True,
            request_id=event.request_id,
        ))

    bus.subscribe(SetTrainSpeed, acknowledge)
    events = _collect(bus, SetTrainSpeed)
    result = await ctx.set_speed("t1", 50)
    assert len(events) == 1
    assert events[0].train_name == "t1"
    assert events[0].speed == 50
    assert result.success


@pytest.mark.parametrize("speed", [-101, 101, True, 1.5])
async def test_set_speed_rejects_invalid_speed(
    ctx: AutomationContext,
    speed: object,
) -> None:
    with pytest.raises(ValueError, match="train speed"):
        await ctx.set_speed("t1", speed)  # type: ignore[arg-type]


async def test_set_speed_raises_when_change_fails(
    bus: EventBus,
    ctx: AutomationContext,
) -> None:
    async def reject(event: SetTrainSpeed) -> None:
        await bus.publish(TrainSpeedChanged(
            train_name=event.train_name,
            speed=event.speed,
            success=False,
            request_id=event.request_id,
        ))

    bus.subscribe(SetTrainSpeed, reject)
    with pytest.raises(RuntimeError, match="train speed change failed"):
        await ctx.set_speed("t1", 50)


async def test_set_speed_serializes_commands_across_contexts(
    bus: EventBus,
    ctx: AutomationContext,
) -> None:
    commands: list[int] = []
    other_context = AutomationContext(bus)

    async def acknowledge(event: SetTrainSpeed) -> None:
        commands.append(event.speed)
        await asyncio.sleep(0.01)
        await bus.publish(TrainSpeedChanged(
            train_name=event.train_name,
            speed=event.speed,
            success=True,
            request_id=event.request_id,
        ))

    bus.subscribe(SetTrainSpeed, acknowledge)
    first, second = await asyncio.gather(
        ctx.set_speed("t1", 10),
        other_context.set_speed("t1", 20),
    )

    assert commands == [10, 20]
    assert (first.speed, second.speed) == (10, 20)


async def test_set_speed_ignores_another_producers_result(
    bus: EventBus,
    ctx: AutomationContext,
) -> None:
    async def acknowledge(event: SetTrainSpeed) -> None:
        await bus.publish(TrainSpeedChanged(
            train_name=event.train_name,
            speed=99,
            success=True,
            request_id="another-request",
        ))
        await bus.publish(TrainSpeedChanged(
            train_name=event.train_name,
            speed=event.speed,
            success=True,
            request_id=event.request_id,
        ))

    bus.subscribe(SetTrainSpeed, acknowledge)

    result = await ctx.set_speed("t1", 20)

    assert result.speed == 20


async def test_set_speed_timeout_covers_dispatch(
    bus: EventBus,
    ctx: AutomationContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancelled = asyncio.Event()

    async def hang(event: SetTrainSpeed) -> None:
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()

    bus.subscribe(SetTrainSpeed, hang)
    monkeypatch.setattr(automation_module, "COMMAND_TIMEOUT", 0.01)

    with pytest.raises(asyncio.TimeoutError):
        await ctx.set_speed("t1", 20)
    assert cancelled.is_set()


async def test_set_switch_with_angle(bus: EventBus, ctx: AutomationContext) -> None:
    _auto_ack_switches(bus)
    events = _collect(bus, SetSwitchPosition)
    result = await ctx.set_switch("hub", "S1", 58)
    assert len(events) == 1
    assert events[0].target == 58
    assert result.ok


async def test_set_switch_with_name(bus: EventBus, ctx: AutomationContext) -> None:
    _auto_ack_switches(bus)
    events = _collect(bus, SetSwitchPosition)
    await ctx.set_switch("hub", "S1", "straight")
    assert events[0].target == "straight"
    await ctx.set_switch("hub", "S1", "diverge")
    assert events[1].target == "diverge"


@pytest.mark.parametrize("target", [-1, 181, True, "left"])
async def test_set_switch_rejects_invalid_target(
    ctx: AutomationContext, target: object
) -> None:
    with pytest.raises(ValueError, match="switch position"):
        await ctx.set_switch("hub", "S1", target)  # type: ignore[arg-type]


async def test_set_switch_raises_when_move_fails(
    bus: EventBus, ctx: AutomationContext
) -> None:
    async def reject(event: SetSwitchPosition) -> None:
        await bus.publish(SwitchPositionChanged(
            hub_name=event.hub_name,
            switch_name=event.switch_name,
            angle=0,
            ok=False,
            request_id=event.request_id,
        ))

    bus.subscribe(SetSwitchPosition, reject)
    with pytest.raises(RuntimeError, match="switch move failed"):
        await ctx.set_switch("hub", "S1", "straight")


async def test_set_switch_timeout_covers_dispatch(
    bus: EventBus,
    ctx: AutomationContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancelled = asyncio.Event()

    async def hang(event: SetSwitchPosition) -> None:
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()

    bus.subscribe(SetSwitchPosition, hang)
    monkeypatch.setattr(automation_module, "COMMAND_TIMEOUT", 0.01)

    with pytest.raises(asyncio.TimeoutError):
        await ctx.set_switch("hub", "S1", "straight")

    assert cancelled.is_set()


async def test_wait_for_resolves(bus: EventBus, ctx: AutomationContext) -> None:
    async def publish_later():
        await asyncio.sleep(0.05)
        await bus.publish(TrainConnected(train_name="t1", ble_address="AA:BB"))

    asyncio.create_task(publish_later())
    event = await ctx.wait_for(TrainConnected)
    assert event.train_name == "t1"


async def test_wait_for_with_filter(bus: EventBus, ctx: AutomationContext) -> None:
    async def publish_later():
        await asyncio.sleep(0.05)
        await bus.publish(TrainConnected(train_name="t1"))
        await asyncio.sleep(0.05)
        await bus.publish(TrainConnected(train_name="t2"))

    asyncio.create_task(publish_later())
    event = await ctx.wait_for(TrainConnected, filter=lambda e: e.train_name == "t2")
    assert event.train_name == "t2"


async def test_wait_for_timeout(bus: EventBus, ctx: AutomationContext) -> None:
    with pytest.raises(asyncio.TimeoutError):
        await ctx.wait_for(TrainConnected, timeout=0.05)


async def test_context_state_is_an_isolated_shared_snapshot(
    bus: EventBus, ctx: AutomationContext
) -> None:
    await bus.publish(TrainSpeedChanged(
        train_name="express", speed=30, success=True
    ))

    snapshot = ctx.state
    snapshot.trains["express"].speed = 90

    assert bus.state.trains["express"].speed == 30


async def test_wait_for_propagates_filter_failure(
    bus: EventBus,
    ctx: AutomationContext,
) -> None:
    def broken_filter(event: TrainConnected) -> bool:
        raise ValueError("broken filter")

    async def publish_later() -> None:
        await asyncio.sleep(0)
        await bus.publish(TrainConnected(train_name="t1"))

    asyncio.create_task(publish_later())
    with pytest.raises(ValueError, match="broken filter"):
        await ctx.wait_for(TrainConnected, filter=broken_filter)


async def test_on_fires_callback(bus: EventBus, ctx: AutomationContext) -> None:
    received = []

    async def callback(event):
        received.append(event)

    ctx.on(TagDetected, callback)
    await bus.publish(TagDetected(hub_name="h", detector_name="D1", train_id="t1"))
    await asyncio.sleep(0.05)
    assert len(received) == 1
    assert received[0].detector_name == "D1"


async def test_on_with_filter(bus: EventBus, ctx: AutomationContext) -> None:
    received = []

    async def callback(event):
        received.append(event)

    ctx.on(TagDetected, callback, filter=lambda e: e.train_id == "t1")
    await bus.publish(TagDetected(hub_name="h", detector_name="D1", train_id="t2"))
    await asyncio.sleep(0.05)
    assert len(received) == 0

    await bus.publish(TagDetected(hub_name="h", detector_name="D1", train_id="t1"))
    await asyncio.sleep(0.05)
    assert len(received) == 1


async def test_on_throttle(bus: EventBus, ctx: AutomationContext) -> None:
    received = []

    async def callback(event):
        received.append(event)

    ctx.on(TagDetected, callback, throttle=0.3)

    # first event fires immediately
    await bus.publish(TagDetected(hub_name="h", detector_name="D1", train_id="t1"))
    await asyncio.sleep(0.05)
    assert len(received) == 1

    # repeats within throttle window are suppressed
    await bus.publish(TagDetected(hub_name="h", detector_name="D1", train_id="t1"))
    await asyncio.sleep(0.05)
    await bus.publish(TagDetected(hub_name="h", detector_name="D1", train_id="t1"))
    await asyncio.sleep(0.05)
    assert len(received) == 1

    # events keep coming — keeps resetting the cooldown
    await asyncio.sleep(0.2)
    await bus.publish(TagDetected(hub_name="h", detector_name="D1", train_id="t1"))
    await asyncio.sleep(0.2)
    await bus.publish(TagDetected(hub_name="h", detector_name="D1", train_id="t1"))
    await asyncio.sleep(0.05)
    assert len(received) == 1

    # quiet for >0.3s — rearms, next event fires
    await asyncio.sleep(0.4)
    await bus.publish(TagDetected(hub_name="h", detector_name="D1", train_id="t1"))
    await asyncio.sleep(0.05)
    assert len(received) == 2
    await ctx.cleanup()


async def test_on_callback_runs_as_task(bus: EventBus, ctx: AutomationContext) -> None:
    started = asyncio.Event()

    async def slow_callback(event):
        started.set()
        await asyncio.sleep(10)

    ctx.on(TrainConnected, slow_callback)
    await bus.publish(TrainConnected(train_name="t1"))
    await asyncio.wait_for(started.wait(), timeout=0.5)
    await ctx.cleanup()


def test_on_rejects_synchronous_callback(ctx: AutomationContext) -> None:
    def callback(event):
        pass

    with pytest.raises(TypeError, match="async def"):
        ctx.on(TrainConnected, callback)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "throttle",
    [0, -0.1, True, "1", float("nan"), float("inf"), 10**1000],
)
def test_on_rejects_invalid_throttle(
    ctx: AutomationContext,
    throttle: object,
) -> None:
    async def callback(event):
        pass

    with pytest.raises(ValueError, match="greater than zero"):
        ctx.on(TrainConnected, callback, throttle=throttle)  # type: ignore[arg-type]


async def test_completed_callback_tasks_are_released(
    bus: EventBus,
    ctx: AutomationContext,
) -> None:
    completed = asyncio.Event()

    async def callback(event):
        completed.set()

    ctx.on(TrainConnected, callback)
    await bus.publish(TrainConnected(train_name="t1"))
    await completed.wait()
    await asyncio.sleep(0)

    assert ctx._tasks == set()


async def test_ramp_speed(bus: EventBus, ctx: AutomationContext) -> None:
    async def acknowledge(event: SetTrainSpeed) -> None:
        await bus.publish(TrainSpeedChanged(
            train_name=event.train_name,
            speed=event.speed,
            success=True,
            request_id=event.request_id,
        ))

    bus.subscribe(SetTrainSpeed, acknowledge)
    events = _collect(bus, SetTrainSpeed)
    await ctx.ramp_speed("t1", 0, 100, duration=0.1, steps=5)
    speeds = [e.speed for e in events]
    assert speeds[0] == 0
    assert speeds[-1] == 100
    assert speeds == sorted(speeds)
    assert len(speeds) == 6


async def test_ramp_speed_final_exact(bus: EventBus, ctx: AutomationContext) -> None:
    async def acknowledge(event: SetTrainSpeed) -> None:
        await bus.publish(TrainSpeedChanged(
            train_name=event.train_name,
            speed=event.speed,
            success=True,
            request_id=event.request_id,
        ))

    bus.subscribe(SetTrainSpeed, acknowledge)
    events = _collect(bus, SetTrainSpeed)
    await ctx.ramp_speed("t1", 0, 77, duration=0.05, steps=3)
    assert events[-1].speed == 77


@pytest.mark.parametrize(
    ("from_speed", "to_speed", "duration", "steps", "message"),
    [
        (-101, 0, 1.0, 10, "train speed"),
        (0, 101, 1.0, 10, "train speed"),
        (0, 10, -1.0, 10, "duration"),
        (0, 10, float("nan"), 10, "duration"),
        (0, 10, float("inf"), 10, "duration"),
        (0, 10, 10**1000, 10, "duration"),
        (0, 10, 1.0, 0, "steps"),
    ],
)
async def test_ramp_speed_rejects_invalid_arguments(
    ctx: AutomationContext,
    from_speed: int,
    to_speed: int,
    duration: float,
    steps: int,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        await ctx.ramp_speed("t1", from_speed, to_speed, duration, steps)


async def test_cleanup_cancels_tasks(bus: EventBus, ctx: AutomationContext) -> None:
    async def long_running():
        await asyncio.sleep(100)

    task = ctx.spawn(long_running())
    assert not task.done()
    await ctx.cleanup()
    assert task.done()


async def test_cleanup_unsubscribes(bus: EventBus, ctx: AutomationContext) -> None:
    received = []

    async def callback(event):
        received.append(event)

    ctx.on(TrainConnected, callback)
    await ctx.cleanup()
    await bus.publish(TrainConnected(train_name="t1"))
    await asyncio.sleep(0.05)
    assert len(received) == 0


async def test_cleanup_cancels_tasks_spawned_during_teardown(
    bus: EventBus,
    ctx: AutomationContext,
) -> None:
    started = asyncio.Event()
    spawned: list[asyncio.Task[None]] = []

    async def callback(event: TrainConnected) -> None:
        try:
            started.set()
            await asyncio.sleep(10)
        finally:
            spawned.append(ctx.spawn(asyncio.sleep(10)))

    ctx.on(TrainConnected, callback)
    await bus.publish(TrainConnected(train_name="t1"))
    await started.wait()

    await ctx.cleanup()

    assert len(spawned) == 1
    assert spawned[0].cancelled()
    assert ctx._tasks == set()


# --- AutomationModule tests ---


async def test_module_runs_script(bus: EventBus) -> None:
    flag = []

    async def script(ctx):
        flag.append(True)

    mod = AutomationModule(bus, script=script)
    await mod.start()
    await asyncio.sleep(0.05)
    assert flag
    await mod.stop()


async def test_module_configures_before_script_starts(bus: EventBus) -> None:
    order = []

    def configure(ctx):
        order.append("configure")

    async def script(ctx):
        order.append("run")

    mod = AutomationModule(bus, configure=configure, script=script)
    await mod.start()
    assert order == ["configure"]
    await asyncio.sleep(0)
    assert order == ["configure", "run"]
    await mod.stop()


async def test_module_stop_cleans_up(bus: EventBus) -> None:
    received = []

    async def script(ctx):
        async def cb(event):
            received.append(event)

        ctx.on(TrainConnected, cb)
        await asyncio.sleep(100)

    mod = AutomationModule(bus, script=script)
    await mod.start()
    await asyncio.sleep(0.05)
    await mod.stop()
    await bus.publish(TrainConnected(train_name="t1"))
    await asyncio.sleep(0.05)
    assert len(received) == 0


async def test_module_stop_cleans_up_subscriptions_registered_during_cancellation(
    bus: EventBus,
) -> None:
    callback_calls: list[TrainConnected] = []
    context: AutomationContext | None = None

    async def callback(event: TrainConnected) -> None:
        callback_calls.append(event)

    async def script(ctx: AutomationContext) -> None:
        nonlocal context
        context = ctx
        try:
            await ctx.forever()
        finally:
            ctx.on(TrainConnected, callback)

    mod = AutomationModule(bus, script=script)
    await mod.start()
    await asyncio.sleep(0)

    await mod.stop()
    await bus.publish(TrainConnected(train_name="t1"))

    assert context is not None
    assert context._subscriptions == []
    assert callback_calls == []


async def test_script_error_logged(bus: EventBus) -> None:
    failed = []

    async def bad_script(ctx):
        raise ValueError("boom")

    mod = AutomationModule(bus, script=bad_script, failure_callback=lambda: failed.append(True))
    await mod.start()
    await asyncio.sleep(0.05)
    assert mod._task.done()
    assert not mod.healthy
    assert failed == [True]
    await mod.stop()


async def test_script_return_triggers_failure_callback(bus: EventBus) -> None:
    failed = []

    async def completed_script(ctx):
        return

    mod = AutomationModule(
        bus, script=completed_script, failure_callback=lambda: failed.append(True)
    )
    await mod.start()
    await asyncio.sleep(0)

    assert not mod.healthy
    assert failed == [True]
    await mod.stop()
