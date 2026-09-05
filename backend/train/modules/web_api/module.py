from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aiohttp import web

from train.core.event_bus import EventBus
from train.core.module import Module
from train.modules.web_api.controller import WebApiController
from train.modules.web_api.transport import WebApiServer

RESPONSE_TIMEOUT = 2.0


class WebApiModule(Module):
    def __init__(
        self,
        bus: EventBus,
        *,
        host: str = "0.0.0.0",
        port: int = 8080,
        shutdown_callback: Callable[[], Any] | None = None,
        readiness_check: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(bus)
        self._controller = WebApiController(
            bus,
            response_timeout=RESPONSE_TIMEOUT,
        )
        self._transport = WebApiServer(
            self._controller,
            host=host,
            port=port,
            shutdown_callback=shutdown_callback,
            readiness_check=readiness_check or (lambda: True),
        )

    @property
    def _app(self) -> web.Application | None:
        return self._transport.application

    async def start(self) -> None:
        self._controller.start()
        try:
            await self._transport.start()
        except Exception:
            self._controller.stop()
            raise

    async def stop(self) -> None:
        try:
            await self._transport.stop()
        finally:
            self._controller.stop()
