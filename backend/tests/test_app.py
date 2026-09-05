import asyncio

import pytest

from train.core.app import App
from train.core.event_bus import EventBus
from train.core.module import Module
from train.domain import Event, SystemShutdown, SystemStarted


class RecorderModule(Module):
    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus)
        self.started = False
        self.stopped = False
        self.events: list[Event] = []

    async def start(self) -> None:
        self.started = True
        self.bus.subscribe(Event, self._on_event)

    async def stop(self) -> None:
        self.stopped = True

    async def _on_event(self, event: Event) -> None:
        self.events.append(event)


async def test_module_lifecycle() -> None:
    app = App()
    mod = app.add_module(RecorderModule)
    assert app._modules == [mod]

    task = asyncio.create_task(app.run())
    await asyncio.sleep(0.05)

    assert mod.started
    assert any(isinstance(e, SystemStarted) for e in mod.events)

    app._shutdown_event.set()
    await task

    assert mod.stopped
    assert any(isinstance(e, SystemShutdown) for e in mod.events)


async def test_stop_order_is_reversed() -> None:
    order: list[str] = []

    class First(Module):
        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            order.append("first")

    class Second(Module):
        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            order.append("second")

    app = App()
    app.add_module(First)
    app.add_module(Second)

    task = asyncio.create_task(app.run())
    await asyncio.sleep(0.05)
    app._shutdown_event.set()
    await task

    assert order == ["second", "first"]
