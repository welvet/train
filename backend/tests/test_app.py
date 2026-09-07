import asyncio

import pytest

from train.core.app import App
from train.core.event_bus import EventBus
from train.core.module import Module
from train.domain import Event, SystemShutdown, SystemStarted
from train.modules.lego_ble import LegoBleModule
from train.modules.web_api import WebApiModule


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
    assert app.bus.state.running is False


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


async def test_cancellation_stops_started_modules() -> None:
    app = App()
    mod = app.add_module(RecorderModule)
    task = asyncio.create_task(app.run())
    await asyncio.sleep(0.05)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert mod.stopped
    assert any(isinstance(event, SystemShutdown) for event in mod.events)
    assert app.bus.state.running is False


async def test_shutdown_continues_after_module_stop_failure() -> None:
    stopped: list[str] = []

    class First(Module):
        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            stopped.append("first")

    class FailingSecond(Module):
        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            stopped.append("second")
            raise RuntimeError("stop failed")

    app = App()
    app.add_module(First)
    app.add_module(FailingSecond)
    task = asyncio.create_task(app.run())
    await asyncio.sleep(0.05)
    app.request_shutdown()

    with pytest.raises(ExceptionGroup, match="Module shutdown failed"):
        await task

    assert stopped == ["second", "first"]
    assert app.bus.state.running is False


async def test_app_shutdown_cancels_active_ble_scan_before_web_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scan_started = asyncio.Event()

    async def scan() -> list[dict[str, object]]:
        scan_started.set()
        await asyncio.Event().wait()
        return []

    monkeypatch.setattr("train.modules.lego_ble.scan_lego_hubs", scan)
    app = App()
    lego = app.add_module(LegoBleModule, train_map={})
    app.add_module(
        WebApiModule,
        host="127.0.0.1",
        port=0,
        ble_scan=lego.scan,
        ble_scan_cancel=lego.cancel_scan,
    )
    app_task = asyncio.create_task(app.run())
    await asyncio.sleep(0.05)
    scan_task = asyncio.create_task(lego.scan())
    await scan_started.wait()

    app.request_shutdown()
    await asyncio.wait_for(app_task, timeout=1)

    with pytest.raises(asyncio.CancelledError):
        await scan_task
