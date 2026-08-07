from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from train.core.event_bus import EventBus
from train.core.events import SystemShutdown, SystemStarted
from train.core.module import Module


class App:
    def __init__(self) -> None:
        self.bus = EventBus()
        self._modules: list[Module] = []
        self._log = logging.getLogger("train.app")
        self._shutdown_event = asyncio.Event()

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    def add_module(self, module_cls: type[Module], **kwargs: Any) -> None:
        mod = module_cls(self.bus, **kwargs)
        self._modules.append(mod)
        self._log.info("Registered module: %s", mod.name)

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._shutdown_event.set)

        for mod in self._modules:
            self._log.info("Starting %s", mod.name)
            await mod.start()

        await self.bus.publish(SystemStarted())
        self._log.info("All modules started. Waiting for shutdown signal.")

        await self._shutdown_event.wait()

        self._log.info("Shutting down...")
        await self.bus.publish(SystemShutdown())

        for mod in reversed(self._modules):
            self._log.info("Stopping %s", mod.name)
            await mod.stop()

        self._log.info("Shutdown complete.")
