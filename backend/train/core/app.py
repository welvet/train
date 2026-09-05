from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any, TypeVar

from train.core.event_bus import EventBus
from train.core.module import Module
from train.domain import SystemShutdown, SystemStarted, SystemState

M = TypeVar("M", bound=Module)


class App:
    def __init__(self, *, state: SystemState | None = None) -> None:
        self.bus = EventBus(state)
        self._modules: list[Module] = []
        self._log = logging.getLogger("train.app")
        self._shutdown_event = asyncio.Event()

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    def add_module(self, module_cls: type[M], **kwargs: Any) -> M:
        mod = module_cls(self.bus, **kwargs)
        self._modules.append(mod)
        self._log.info("Registered module: %s", mod.name)
        return mod

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        installed_signals: list[signal.Signals] = []
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._shutdown_event.set)
            installed_signals.append(sig)

        started_modules: list[Module] = []
        run_error: BaseException | None = None
        try:
            for mod in self._modules:
                self._log.info("Starting %s", mod.name)
                started_modules.append(mod)
                await mod.start()

            await self.bus.publish(SystemStarted())
            self._log.info("All modules started. Waiting for shutdown signal.")
            await self._shutdown_event.wait()
        except BaseException as exc:
            run_error = exc

        self._log.info("Shutting down...")
        stop_errors: list[Exception] = []
        try:
            await self.bus.publish(SystemShutdown())
            for mod in reversed(started_modules):
                self._log.info("Stopping %s", mod.name)
                try:
                    await mod.stop()
                except Exception as exc:
                    stop_errors.append(exc)
                    self._log.error("Failed to stop %s", mod.name, exc_info=True)
        finally:
            for sig in installed_signals:
                loop.remove_signal_handler(sig)

        self._log.info("Shutdown complete.")
        if run_error is not None:
            if stop_errors:
                self._log.error(
                    "Suppressed %d shutdown error(s) while propagating %s",
                    len(stop_errors),
                    type(run_error).__name__,
                )
            raise run_error
        if stop_errors:
            raise ExceptionGroup("Module shutdown failed", stop_errors)
