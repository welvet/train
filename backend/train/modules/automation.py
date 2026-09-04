from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Any, Callable, Coroutine, TypeVar

from train.core.event_bus import EventBus
from train.core.events.base import Event
from train.core.events.hub import SetSwitchPosition, SwitchPositionChanged
from train.core.events.system import AutomationHalt, AutomationResume
from train.core.events.train import SetTrainSpeed
from train.core.module import Module

STRAIGHT = 58
DIVERGE = 100
SWITCH_POSITIONS = {"straight": STRAIGHT, "diverge": DIVERGE}

E = TypeVar("E", bound=Event)
ScriptFn = Callable[["AutomationContext"], Coroutine[Any, Any, None]]


class AutomationContext:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._tasks: list[asyncio.Task[Any]] = []
        self._subscriptions: list[tuple[type[Event], Any]] = []
        self.halted = False

    async def set_speed(self, train: str, speed: int) -> None:
        await self._bus.publish(SetTrainSpeed(train_name=train, speed=speed))

    async def set_switch(self, hub: str, switch: str, position: str | int) -> None:
        if isinstance(position, str):
            angle = SWITCH_POSITIONS[position]
        else:
            angle = position

        future: asyncio.Future[SwitchPositionChanged] = asyncio.get_running_loop().create_future()

        async def _on_ack(event: SwitchPositionChanged) -> None:
            if event.hub_name == hub and event.switch_name == switch and not future.done():
                future.set_result(event)

        self._bus.subscribe(SwitchPositionChanged, _on_ack)
        try:
            await self._bus.publish(SetSwitchPosition(hub_name=hub, switch_name=switch, angle=angle))
            await asyncio.wait_for(future, timeout=3.0)
        finally:
            self._bus.unsubscribe(SwitchPositionChanged, _on_ack)

    async def wait_for(
        self,
        event_type: type[E],
        *,
        filter: Callable[[E], bool] | None = None,
        timeout: float | None = None,
    ) -> E:
        future: asyncio.Future[E] = asyncio.get_running_loop().create_future()

        async def _handler(event: E) -> None:
            if future.done():
                return
            if filter is not None and not filter(event):
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
        await asyncio.sleep(seconds)

    def on(
        self,
        event_type: type[E],
        callback: Callable[[E], Coroutine[Any, Any, None]],
        *,
        filter: Callable[[E], bool] | None = None,
        throttle: float | None = None,
    ) -> None:
        last_seen: float = 0.0
        armed: bool = True

        async def _rearm() -> None:
            nonlocal armed
            while True:
                await asyncio.sleep(0.1)
                if not armed and asyncio.get_event_loop().time() - last_seen >= throttle:
                    armed = True
                    return

        rearm_task: asyncio.Task[None] | None = None

        async def _handler(event: E) -> None:
            nonlocal last_seen, armed, rearm_task
            if self.halted:
                return
            if filter is not None and not filter(event):
                return
            if throttle is not None:
                last_seen = asyncio.get_event_loop().time()
                if not armed:
                    return
                armed = False
                rearm_task = asyncio.create_task(_rearm())
                self._tasks.append(rearm_task)
            task = asyncio.create_task(callback(event))
            self._tasks.append(task)

        self._bus.subscribe(event_type, _handler)
        self._subscriptions.append((event_type, _handler))

    async def ramp_speed(
        self, train: str, from_speed: int, to_speed: int, duration: float, steps: int = 10,
    ) -> None:
        step_delay = duration / steps
        for i in range(steps + 1):
            speed = round(from_speed + (to_speed - from_speed) * i / steps)
            await self.set_speed(train, speed)
            if i < steps:
                await asyncio.sleep(step_delay)

    def spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro)
        self._tasks.append(task)
        return task

    async def cleanup(self) -> None:
        for task in self._tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        for event_type, handler in self._subscriptions:
            with suppress(ValueError):
                self._bus.unsubscribe(event_type, handler)
        self._subscriptions.clear()


class AutomationModule(Module):
    def __init__(self, bus: EventBus, *, script: ScriptFn) -> None:
        super().__init__(bus)
        self._script = script
        self._ctx: AutomationContext | None = None
        self._task: asyncio.Task[None] | None = None
        self._log = logging.getLogger("train.automation")

    async def start(self) -> None:
        self._ctx = AutomationContext(self.bus)
        self.bus.subscribe(AutomationHalt, self._on_halt)
        self.bus.subscribe(AutomationResume, self._on_resume)
        self._task = asyncio.create_task(self._run_script())
        # Let the script install event subscriptions before hardware modules start.
        await asyncio.sleep(0)

    async def _on_halt(self, event: AutomationHalt) -> None:
        self._log.info("Automation halted")
        self.halted = True

    async def _on_resume(self, event: AutomationResume) -> None:
        self._log.info("Automation resumed")
        self.halted = False

    async def _run_script(self) -> None:
        try:
            await self._script(self._ctx)
        except asyncio.CancelledError:
            pass
        except Exception:
            self._log.error("Automation script failed", exc_info=True)

    @property
    def halted(self) -> bool:
        return self._ctx.halted if self._ctx else False

    @halted.setter
    def halted(self, value: bool) -> None:
        if self._ctx:
            self._ctx.halted = value

    async def stop(self) -> None:
        if self._ctx:
            await self._ctx.cleanup()
        if self._task and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
