from __future__ import annotations

import asyncio
import inspect
import logging
import math
from contextlib import suppress
from typing import Any, Callable, Coroutine, TypeVar

from train.core.event_bus import CommandFailed, CommandResourceNotFound, EventBus
from train.core.module import Module
from train.domain import (
    AutomationHalt,
    AutomationResume,
    Event,
    SetSwitchPosition,
    SetTrainSpeed,
    SwitchPositionChanged,
    SystemState,
    TrainSpeedChanged,
)

E = TypeVar("E", bound=Event)
ScriptFn = Callable[["AutomationContext"], Coroutine[Any, Any, None]]
ConfigureFn = Callable[["AutomationContext"], None]
COMMAND_TIMEOUT = 3.0


class AutomationContext:
    """Stable interface exposed to an installation's automation program."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._tasks: set[asyncio.Task[Any]] = set()
        self._subscriptions: list[tuple[type[Event], Any]] = []
        self._log = logging.getLogger("train.automation")
        self._closing = False

    @property
    def state(self) -> SystemState:
        """Return an isolated snapshot of the current railway state."""
        return self._bus.state

    @property
    def halted(self) -> bool:
        return self._bus.state.automation.halted

    @staticmethod
    def _is_finite_number(value: object) -> bool:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        try:
            return math.isfinite(value)
        except OverflowError:
            return False

    @staticmethod
    def _validate_event_type(event_type: type[Event]) -> None:
        if not inspect.isclass(event_type) or not issubclass(event_type, Event):
            raise TypeError("event_type must be an Event class")

    def _track_task(self, task: asyncio.Task[Any]) -> None:
        self._tasks.add(task)
        if self._closing:
            task.cancel()

        def _completed(completed: asyncio.Task[Any]) -> None:
            self._tasks.discard(completed)
            if completed.cancelled():
                return
            error = completed.exception()
            if error is not None:
                self._log.error(
                    "Automation task failed: %s",
                    error,
                    exc_info=error,
                )

        task.add_done_callback(_completed)

    async def set_speed(self, train: str, speed: int) -> TrainSpeedChanged:
        """Set a train's signed speed and return its successful acknowledgement."""
        if (
            isinstance(speed, bool)
            or not isinstance(speed, int)
            or not -100 <= speed <= 100
        ):
            raise ValueError("train speed must be an integer in -100..100")

        command = SetTrainSpeed(train_name=train, speed=speed)
        try:
            result = await self._bus.dispatch(command, timeout=COMMAND_TIMEOUT)
        except (CommandFailed, CommandResourceNotFound) as exc:
            raise RuntimeError(f"train speed change failed: {train}") from exc
        if not isinstance(result, TrainSpeedChanged):
            raise RuntimeError("train speed command returned an invalid response")
        return result

    async def set_switch(
        self,
        hub: str,
        switch: str,
        position: str | int,
    ) -> SwitchPositionChanged:
        """Move a switch and return its successful acknowledgement."""
        if isinstance(position, bool) or not (
            isinstance(position, int) and 0 <= position <= 180
            or isinstance(position, str) and position in {"straight", "diverge"}
        ):
            raise ValueError(
                "switch position must be straight, diverge, or an angle in 0..180"
            )
        command = SetSwitchPosition(
            hub_name=hub,
            switch_name=switch,
            target=position,
        )
        try:
            result = await self._bus.dispatch(command, timeout=COMMAND_TIMEOUT)
        except (CommandFailed, CommandResourceNotFound) as exc:
            raise RuntimeError(f"switch move failed: {hub}/{switch}") from exc
        if not isinstance(result, SwitchPositionChanged):
            raise RuntimeError("switch command returned an invalid response")
        return result

    async def wait_for(
        self,
        event_type: type[E],
        *,
        filter: Callable[[E], bool] | None = None,
        timeout: float | None = None,
    ) -> E:
        """Wait for and return the next event accepted by the optional filter."""
        self._validate_event_type(event_type)
        future: asyncio.Future[E] = asyncio.get_running_loop().create_future()

        async def _handler(event: E) -> None:
            if future.done():
                return
            if filter is not None:
                try:
                    if not filter(event):
                        return
                except Exception as exc:
                    future.set_exception(exc)
                    return
            future.set_result(event)

        self._bus.subscribe(event_type, _handler)
        try:
            if timeout is not None:
                return await asyncio.wait_for(future, timeout=timeout)
            return await future
        finally:
            self._bus.unsubscribe(event_type, _handler)

    async def sleep(self, seconds: float) -> None:
        """Sleep without blocking the backend event loop."""
        await asyncio.sleep(seconds)

    async def forever(self) -> None:
        """Keep the automation program alive until backend shutdown."""
        await self.wait_for(Event, filter=lambda _: False)

    def on(
        self,
        event_type: type[E],
        callback: Callable[[E], Coroutine[Any, Any, None]],
        *,
        filter: Callable[[E], bool] | None = None,
        throttle: float | None = None,
    ) -> None:
        """Register an asynchronous callback for future matching events."""
        self._validate_event_type(event_type)
        if not inspect.iscoroutinefunction(callback):
            raise TypeError("callback must be defined with async def")
        if throttle is not None and (
            not self._is_finite_number(throttle) or throttle <= 0
        ):
            raise ValueError("throttle must be a finite number greater than zero")

        last_seen: float = 0.0
        armed: bool = True

        async def _rearm() -> None:
            nonlocal armed
            while True:
                await asyncio.sleep(0.1)
                if not armed and asyncio.get_event_loop().time() - last_seen >= throttle:
                    armed = True
                    return

        async def _handler(event: E) -> None:
            nonlocal last_seen, armed
            if self._closing or self.halted:
                return
            if filter is not None and not filter(event):
                return
            if throttle is not None:
                last_seen = asyncio.get_event_loop().time()
                if not armed:
                    return
                armed = False
                self._track_task(asyncio.create_task(_rearm()))
            task = asyncio.create_task(callback(event))
            self._track_task(task)

        self._bus.subscribe(event_type, _handler)
        self._subscriptions.append((event_type, _handler))

    async def ramp_speed(
        self, train: str, from_speed: int, to_speed: int, duration: float, steps: int = 10,
    ) -> None:
        """Move between two signed speeds through acknowledged intermediate steps."""
        for speed in (from_speed, to_speed):
            if (
                isinstance(speed, bool)
                or not isinstance(speed, int)
                or not -100 <= speed <= 100
            ):
                raise ValueError("train speed must be an integer in -100..100")
        if isinstance(steps, bool) or not isinstance(steps, int) or steps <= 0:
            raise ValueError("steps must be a positive integer")
        if not self._is_finite_number(duration) or duration < 0:
            raise ValueError("duration must be a finite number zero or greater")

        step_delay = duration / steps
        for i in range(steps + 1):
            speed = round(from_speed + (to_speed - from_speed) * i / steps)
            await self.set_speed(train, speed)
            if i < steps:
                await asyncio.sleep(step_delay)

    def spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        """Start background work that is logged and cancelled with the automation."""
        task = asyncio.create_task(coro)
        self._track_task(task)
        return task

    async def cleanup(self) -> None:
        self._closing = True
        for event_type, handler in self._subscriptions:
            with suppress(ValueError):
                self._bus.unsubscribe(event_type, handler)
        self._subscriptions.clear()
        while self._tasks:
            tasks = list(self._tasks)
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._tasks.difference_update(tasks)


class AutomationModule(Module):
    def __init__(
        self,
        bus: EventBus,
        *,
        script: ScriptFn,
        configure: ConfigureFn | None = None,
        failure_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(bus)
        self._script = script
        self._configure = configure or (lambda _: None)
        self._failure_callback = failure_callback
        self._ctx: AutomationContext | None = None
        self._task: asyncio.Task[None] | None = None
        self._log = logging.getLogger("train.automation")
        self._failure: str | None = None

    async def start(self) -> None:
        self._ctx = AutomationContext(self.bus)
        self.bus.subscribe(AutomationHalt, self._on_halt)
        self.bus.subscribe(AutomationResume, self._on_resume)
        self._configure(self._ctx)
        self._task = asyncio.create_task(self._run_script())

    async def _on_halt(self, event: AutomationHalt) -> None:
        self._log.info("Automation halted")

    async def _on_resume(self, event: AutomationResume) -> None:
        self._log.info("Automation resumed")

    async def _run_script(self) -> None:
        try:
            await self._script(self._ctx)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            self._failure = str(exc)
            self._log.error("Automation script failed", exc_info=True)
        else:
            self._failure = "automation script returned unexpectedly"
            self._log.error(self._failure)
        if self._failure_callback is not None:
            self._failure_callback()

    @property
    def healthy(self) -> bool:
        return self._task is not None and not self._task.done() and self._failure is None

    @property
    def halted(self) -> bool:
        return self.bus.state.automation.halted

    async def stop(self) -> None:
        with suppress(ValueError):
            self.bus.unsubscribe(AutomationHalt, self._on_halt)
        with suppress(ValueError):
            self.bus.unsubscribe(AutomationResume, self._on_resume)
        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        if self._ctx:
            await self._ctx.cleanup()
