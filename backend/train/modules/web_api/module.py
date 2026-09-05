from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from aiohttp import web

from train.core.event_bus import EventBus
from train.core.module import Module
from train.modules.web_api.transport import WebApiServer


class WebApiModule(Module):
    def __init__(
        self,
        bus: EventBus,
        *,
        host: str = "0.0.0.0",
        port: int = 8080,
        readiness_check: Callable[[], bool] | None = None,
        static_root: Path | None = None,
    ) -> None:
        super().__init__(bus)
        self._transport = WebApiServer(
            bus,
            host=host,
            port=port,
            readiness_check=readiness_check or (lambda: True),
            static_root=static_root,
        )

    @property
    def _app(self) -> web.Application | None:
        return self._transport.application

    async def start(self) -> None:
        await self._transport.start()

    async def stop(self) -> None:
        await self._transport.stop()
