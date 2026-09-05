# Writing automations

An automation is the installation-specific `automation.py` in the local
railway workspace. The backend imports it once at startup and gives it an
`AutomationContext` for observing railway events and sending commands.

`AutomationContext` and the observation events listed in this guide are the
public, stable automation surface. Import them through these modules:

```python
from train.automation import AutomationContext
from train.domain import HubConnected, SystemStarted, TagDetected, TagRemoved
```

Do not import from `train.core` or `train.modules`; those packages are backend
implementation details. `train.domain` also exports command and backend state
types for product code; only the observation events listed under [Events](#events)
are part of the automation contract.

## Minimal program

Every program must define both entry points. `configure` is synchronous so it
can register handlers before hardware modules start. `run` is asynchronous and
must remain alive for the lifetime of the backend.

```python
from train.automation import AutomationContext
from train.domain import TagDetected


async def on_arrival(event: TagDetected) -> None:
    if event.detector_name == "entry":
        print(f"{event.train_id} entered {event.hub_name}")


def configure(ctx: AutomationContext) -> None:
    ctx.on(TagDetected, on_arrival)


async def run(ctx: AutomationContext) -> None:
    await ctx.forever()
```

The startup order is:

```text
load automation.py
  -> configure(ctx)
  -> start automation run task
  -> start train, Arduino, and web modules
  -> publish SystemStarted
```

Put event registration in `configure`, not at the beginning of `run`; the run
task is scheduled asynchronously and startup events could otherwise arrive
first. If `run` raises or returns, the automation becomes unhealthy and the
backend shuts down.

## Context API

All command methods are asynchronous. Await them so failures reach the caller.
Commands targeting the same train or switch are serialized across all
automation contexts and HTTP callers. Every command also carries an end-to-end
correlation ID, so concurrent commands cannot consume one another's
acknowledgement.
If a command times out, its physical outcome is unknown because the hardware
write may already have happened; inspect observed state before retrying rather
than retrying blindly.

### `await ctx.set_speed(train, speed)`

Sets a train's signed motor speed. `speed` must be an integer from `-100` to
`100`; zero stops the train and negative values reverse it. The call waits for
the BLE write result and returns its `TrainSpeedChanged` event. Success means
the hub accepted the write; it does not measure whether the train has reached
the requested speed. The method raises `ValueError` for an invalid speed,
`RuntimeError` when the train is disconnected or the write fails, and
`asyncio.TimeoutError` when no result arrives within three seconds.

```python
result = await ctx.set_speed("my_train", -40)
print(result.train_name, result.speed, result.success)
```

### `await ctx.set_switch(hub, switch, position)`

Moves a switch and waits for its acknowledgement. `position` is `"straight"`,
`"diverge"`, or a servo angle from `0` through `180`. The successful
`SwitchPositionChanged` event is returned. The acknowledgement means the
firmware accepted the target and issued the servo command; there is no physical
position sensor, and the call does not wait for the servo's configured settle
period. Add an appropriate `ctx.sleep(...)` before allowing a train onto the
switch. Invalid positions raise `ValueError`; a rejected move raises
`RuntimeError`; a missing result raises `asyncio.TimeoutError` after three
seconds.

```python
result = await ctx.set_switch("my_hub", "S1", "diverge")
print(result.angle)
```

### `await ctx.wait_for(event_type, *, filter=None, timeout=None)`

Waits for the next matching event and returns it. It does not replay current or
historical state. Use `timeout` when the event might never arrive and handle
`asyncio.TimeoutError` if that is an expected outcome.

```python
event = await ctx.wait_for(
    TagDetected,
    filter=lambda item: item.detector_name == "entry",
    timeout=30,
)
```

### `ctx.on(event_type, callback, *, filter=None, throttle=None)`

Registers an async callback. Call it from `configure` when startup events
matter. Each accepted event starts a separate task, so callbacks may overlap
and shared state needs an `asyncio.Lock` or a queue.

`filter` accepts an event when it returns true. A finite, positive `throttle`
runs the first matching event immediately, suppresses subsequent matches, and
rearms only after that many quiet seconds. It is useful for noisy sensors, but
it does not queue or replay suppressed events. Callback failures are logged.

```python
def configure(ctx: AutomationContext) -> None:
    ctx.on(
        TagDetected,
        on_arrival,
        filter=lambda event: event.detector_name == "entry",
        throttle=0.5,
    )
```

The callback must be declared with `async def`. Registrations are removed and
outstanding callback tasks are cancelled during shutdown.

### `await ctx.ramp_speed(train, from_speed, to_speed, duration, steps=10)`

Sends `steps + 1` acknowledged speed commands, including both endpoints. Speeds
must be in `-100..100`, `duration` must be a finite non-negative number, and
`steps` must be a positive integer. The requested duration covers the sleeps
between steps; hardware acknowledgement time can make the complete ramp
slightly longer.

### `await ctx.sleep(seconds)`

Sleeps without blocking the event loop. Prefer it to `time.sleep`, which would
prevent hardware and API tasks from making progress.

### `ctx.spawn(coroutine)`

Starts background work owned by the automation and returns its `asyncio.Task`.
Owned tasks are cancelled at shutdown, completed tasks are released, and task
failures are logged. Use this instead of a bare `asyncio.create_task` when the
work should follow the automation lifecycle.

### `await ctx.forever()`

Waits until the automation is cancelled during backend shutdown. This is the
usual body of `run` when all behavior is registered through `ctx.on`.

### `ctx.halted`

Reports whether an `automation_halt` event has halted registered automation
callbacks. While halted, new `ctx.on` callbacks are skipped; they are not queued
for resume. Halt does not stop a moving train, cancel a callback already in
progress, or pause logic running directly in `run` or `ctx.spawn`. Safety logic
should therefore stop trains explicitly and use `ctx.halted` where background
loops must honor the operator halt.

## Events

Every event is an immutable dataclass with a Unix `timestamp`. Import event
classes from `train.domain` and access their fields directly.

| Event | Fields | Meaning |
| --- | --- | --- |
| `SystemStarted` | — | All backend modules have started. |
| `TrainConnected` | `train_name`, `ble_address` | BLE train became available. |
| `TrainDisconnected` | `train_name`, `ble_address` | BLE train became unavailable. |
| `TrainSpeedChanged` | `train_name`, `speed`, `success`, `request_id` | A speed-command BLE write completed. |
| `TrainStatus` | `train_name`, `battery_pct`, `voltage` | Periodic train telemetry. |
| `HubConnected` | `hub_name`, `switches`, `detectors`, `active_trains` | Arduino hub connected and supplied its topology and current detections. |
| `HubDisconnected` | `hub_name` | Arduino hub disconnected. |
| `SwitchPositionChanged` | `hub_name`, `switch_name`, `angle`, `ok`, `request_id` | Firmware accepted or rejected a switch target. |
| `TagDetected` | `hub_name`, `detector_name`, `train_id` | A known train tag appeared at a detector. |
| `TagRemoved` | `hub_name`, `detector_name`, `train_id` | That train tag left the detector. |

`HubConnected.active_trains` is a tuple of `(detector_name, train_id)` pairs.
It is the reconnect snapshot; use it to initialize state that would otherwise
depend on detection events emitted while the hub was offline.

`SetTrainSpeed` and `SetSwitchPosition` are command events used by the context
helpers and the public event transport. Automation programs should call
`set_speed` and `set_switch` so they get validation, acknowledgement, and
timeout handling.
`AutomationHalt`, `AutomationResume`, and `SystemShutdown` are backend control
events, not supported automation callbacks. Use `ctx.halted` for halt state;
automation work is cancelled during shutdown rather than given a cleanup-event
deadline.

## A serialized controller

For multi-step railway behavior, feed callbacks into one queue and let a single
worker own state and hardware commands. This avoids two detections changing the
same switch or train concurrently.

```python
import asyncio

from train.automation import AutomationContext
from train.domain import SystemStarted, TagDetected

signals: asyncio.Queue[TagDetected] = asyncio.Queue()


async def enqueue(event: TagDetected) -> None:
    await signals.put(event)


async def controller(ctx: AutomationContext) -> None:
    while True:
        event = await signals.get()
        if ctx.halted:
            continue
        if event.detector_name == "entry":
            await ctx.set_switch(event.hub_name, "S1", "straight")
            await ctx.ramp_speed(event.train_id, 0, 45, duration=2)


async def start_controller(event: SystemStarted, ctx: AutomationContext) -> None:
    ctx.spawn(controller(ctx))


def configure(ctx: AutomationContext) -> None:
    ctx.on(TagDetected, enqueue)

    async def start(event: SystemStarted) -> None:
        await start_controller(event, ctx)

    ctx.on(SystemStarted, start)


async def run(ctx: AutomationContext) -> None:
    await ctx.forever()
```

## Validate and run

From the repository root:

```sh
tools/data validate
cd backend
.venv/bin/python -m train
```

The backend does not reload `automation.py`; restart it after edits. Submit
`automation_halt` and `automation_resume` events through `POST /api/events` to
pause and resume registered callbacks.

Switch command correlation requires the Arduino firmware shipped with the same
or a newer repository revision. During an upgrade, flash the Arduino before
restarting the updated backend. The older backend safely ignores the additional
correlation field sent by newer firmware.
