from __future__ import annotations

import asyncio
import logging
from enum import Enum, auto

from train.core.events.hub import DetectorChanged
from train.modules.automation import AutomationContext

TRAIN = "arctic_express"
HUB = "A_HUB_1"
PITSTOP_DETECTOR = "D1"
ARMING_DETECTOR = "D2"
PITSTOP_SWITCH = "S2"
CRUISE_SPEED = 80


class PitStopState(Enum):
    NORMAL = auto()
    PITSTOP_ARMED = auto()
    ENTERING_PITSTOP = auto()
    PITSTOP_DWELL = auto()
    COMING_FROM_PITSTOP = auto()


class PitStopSignal(Enum):
    START = auto()
    D1_TRIGGERED = auto()
    D2_TRIGGERED = auto()
    ENTRY_TIMER_ELAPSED = auto()
    DWELL_TIMER_ELAPSED = auto()


class PitStopController:
    """Owns all pit-stop state transitions and their hardware effects."""

    def __init__(
        self,
        ctx: AutomationContext,
        *,
        entry_delay: float = 3.0,
        dwell_time: float = 2.0,
    ) -> None:
        self._ctx = ctx
        self._entry_delay = entry_delay
        self._dwell_time = dwell_time
        self._queue: asyncio.Queue[
            tuple[PitStopSignal, asyncio.Future[None]]
        ] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        self._timers: set[asyncio.Task[None]] = set()
        self._log = logging.getLogger("train.pitstop")
        self.state = PitStopState.PITSTOP_ARMED

    @property
    def should_pitstop(self) -> bool:
        """Whether the next D1 pass should send the train into the pit stop."""
        return self.state is PitStopState.PITSTOP_ARMED

    async def start(self) -> None:
        self._worker = asyncio.create_task(self._run(), name="pitstop-controller")
        await self.handle(PitStopSignal.START)

    async def stop(self) -> None:
        for timer in self._timers:
            timer.cancel()
        await asyncio.gather(*self._timers, return_exceptions=True)
        self._timers.clear()

        if self._worker is not None:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None

    async def on_detector(self, event: DetectorChanged) -> None:
        signal = {
            PITSTOP_DETECTOR: PitStopSignal.D1_TRIGGERED,
            ARMING_DETECTOR: PitStopSignal.D2_TRIGGERED,
        }.get(event.detector_name)
        if signal is not None:
            await self.handle(signal)

    async def handle(self, signal: PitStopSignal) -> None:
        if self._worker is None:
            raise RuntimeError("PitStopController has not been started")
        completed = asyncio.get_running_loop().create_future()
        await self._queue.put((signal, completed))
        await completed

    async def _run(self) -> None:
        while True:
            signal, completed = await self._queue.get()
            try:
                await self._transition(signal)
            except Exception as exc:
                if not completed.done():
                    completed.set_exception(exc)
                self._log.exception("Pit-stop transition failed for %s", signal.name)
            else:
                if not completed.done():
                    completed.set_result(None)
            finally:
                self._queue.task_done()

    async def _transition(self, signal: PitStopSignal) -> None:
        previous = self.state

        if signal is PitStopSignal.START:
            await self._ctx.set_switch(HUB, PITSTOP_SWITCH, "diverge")

        elif self.state is PitStopState.PITSTOP_ARMED:
            if signal is PitStopSignal.D1_TRIGGERED:
                self.state = PitStopState.ENTERING_PITSTOP
                self._start_timer(self._entry_delay, PitStopSignal.ENTRY_TIMER_ELAPSED)

        elif self.state is PitStopState.ENTERING_PITSTOP:
            if signal is PitStopSignal.ENTRY_TIMER_ELAPSED:
                self.state = PitStopState.PITSTOP_DWELL
                await self._ctx.set_speed(TRAIN, 0)
                self._start_timer(self._dwell_time, PitStopSignal.DWELL_TIMER_ELAPSED)

        elif self.state is PitStopState.PITSTOP_DWELL:
            if signal is PitStopSignal.DWELL_TIMER_ELAPSED:
                await self._ctx.set_speed(TRAIN, CRUISE_SPEED)
                self.state = PitStopState.COMING_FROM_PITSTOP

        elif self.state is PitStopState.COMING_FROM_PITSTOP:
            if signal is PitStopSignal.D1_TRIGGERED:
                await self._ctx.set_speed(TRAIN, 0)
                await self._ctx.set_switch(HUB, PITSTOP_SWITCH, "straight")
                await self._ctx.set_speed(TRAIN, CRUISE_SPEED)
                self.state = PitStopState.NORMAL

        elif self.state is PitStopState.NORMAL:
            if signal is PitStopSignal.D2_TRIGGERED:
                await self._ctx.set_switch(HUB, PITSTOP_SWITCH, "diverge")
                self.state = PitStopState.PITSTOP_ARMED

        if self.state is not previous:
            self._log.info(
                "Pit-stop state: %s -> %s (%s)",
                previous.name,
                self.state.name,
                signal.name,
            )

    def _start_timer(self, delay: float, signal: PitStopSignal) -> None:
        async def fire() -> None:
            await self._ctx.sleep(delay)
            await self.handle(signal)

        timer = asyncio.create_task(fire(), name=f"pitstop:{signal.name.lower()}")
        self._timers.add(timer)
        timer.add_done_callback(self._timer_finished)

    def _timer_finished(self, timer: asyncio.Task[None]) -> None:
        self._timers.discard(timer)
        if not timer.cancelled():
            timer.exception()
