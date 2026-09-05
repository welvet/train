from __future__ import annotations

import asyncio
from typing import Any

from train.core.event_bus import EventBus
from train.core.module import Module
from train.domain import SetSwitchPosition, TrainTagRegistry
from train.modules.arduino_hub.controller import ArduinoHubController, HubClient
from train.modules.arduino_hub.transport import ArduinoHubServer


class ArduinoHubModule(Module):
    def __init__(
        self,
        bus: EventBus,
        *,
        host: str = "0.0.0.0",
        port: int = 9000,
        train_tag_map: dict[str, str] | None = None,
        hub_config: dict[str, dict[str, Any]],
    ) -> None:
        super().__init__(bus)
        self._controller = ArduinoHubController(
            bus,
            train_tags=TrainTagRegistry(train_tag_map),
            hub_config=hub_config,
        )
        self._transport = ArduinoHubServer(
            host,
            port,
            on_message=self._controller.handle_message,
            on_disconnect=self._controller.disconnect,
        )

    @property
    def _server(self) -> asyncio.Server | None:
        return self._transport.server

    @property
    def _clients(self) -> dict[str, HubClient]:
        return self._controller.clients

    async def start(self) -> None:
        self.bus.subscribe(SetSwitchPosition, self._controller.set_switch)
        await self._transport.start()

    async def stop(self) -> None:
        await self._transport.stop()

    def get_hub_info(self, hub_name: str) -> dict[str, Any] | None:
        return self._controller.get_hub_info(hub_name)
