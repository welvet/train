from __future__ import annotations

import asyncio
from typing import Any

from train.core.event_bus import EventBus
from train.domain import (
    AutomationHalt,
    AutomationResume,
    HubConnected,
    HubDisconnected,
    HubState,
    SetSwitchPosition,
    SetTrainSpeed,
    SwitchPositionChanged,
    TagDetected,
    TagRemoved,
    TrainConnected,
    TrainDisconnected,
    TrainSpeedChanged,
    TrainStatus,
)


class WebApiController:
    def __init__(self, bus: EventBus, *, response_timeout: float) -> None:
        self._bus = bus
        self._response_timeout = response_timeout
        self._trains: dict[str, dict[str, Any]] = {}
        self._hubs: dict[str, HubState] = {}
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._bus.subscribe(TrainConnected, self._on_train_connected)
        self._bus.subscribe(TrainDisconnected, self._on_train_disconnected)
        self._bus.subscribe(TrainSpeedChanged, self._on_train_speed_changed)
        self._bus.subscribe(TrainStatus, self._on_train_status)
        self._bus.subscribe(HubConnected, self._on_hub_connected)
        self._bus.subscribe(HubDisconnected, self._on_hub_disconnected)
        self._bus.subscribe(SwitchPositionChanged, self._on_switch_changed)
        self._bus.subscribe(TagDetected, self._on_tag_detected)
        self._bus.subscribe(TagRemoved, self._on_tag_removed)
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self._bus.unsubscribe(TrainConnected, self._on_train_connected)
        self._bus.unsubscribe(TrainDisconnected, self._on_train_disconnected)
        self._bus.unsubscribe(TrainSpeedChanged, self._on_train_speed_changed)
        self._bus.unsubscribe(TrainStatus, self._on_train_status)
        self._bus.unsubscribe(HubConnected, self._on_hub_connected)
        self._bus.unsubscribe(HubDisconnected, self._on_hub_disconnected)
        self._bus.unsubscribe(SwitchPositionChanged, self._on_switch_changed)
        self._bus.unsubscribe(TagDetected, self._on_tag_detected)
        self._bus.unsubscribe(TagRemoved, self._on_tag_removed)
        self._started = False

    def get_train(self, train_name: str) -> dict[str, Any] | None:
        return self._trains.get(train_name)

    def get_hub(self, hub_name: str) -> HubState | None:
        return self._hubs.get(hub_name)

    async def set_train_speed(
        self,
        train_name: str,
        speed: int,
    ) -> TrainSpeedChanged:
        command = SetTrainSpeed(train_name=train_name, speed=speed)
        future: asyncio.Future[TrainSpeedChanged] = (
            asyncio.get_running_loop().create_future()
        )

        async def on_response(event: TrainSpeedChanged) -> None:
            if event.request_id == command.request_id and not future.done():
                future.set_result(event)

        async def dispatch() -> TrainSpeedChanged:
            await self._bus.publish(command)
            return await future

        self._bus.subscribe(TrainSpeedChanged, on_response)
        try:
            return await asyncio.wait_for(
                dispatch(),
                timeout=self._response_timeout,
            )
        finally:
            self._bus.unsubscribe(TrainSpeedChanged, on_response)

    async def set_switch_position(
        self,
        hub_name: str,
        switch_name: str,
        target: str | int,
    ) -> SwitchPositionChanged:
        command = SetSwitchPosition(
            hub_name=hub_name,
            switch_name=switch_name,
            target=target,
        )
        future: asyncio.Future[SwitchPositionChanged] = (
            asyncio.get_running_loop().create_future()
        )

        async def on_response(event: SwitchPositionChanged) -> None:
            if event.request_id == command.request_id and not future.done():
                future.set_result(event)

        async def dispatch() -> SwitchPositionChanged:
            await self._bus.publish(command)
            return await future

        self._bus.subscribe(SwitchPositionChanged, on_response)
        try:
            return await asyncio.wait_for(
                dispatch(),
                timeout=self._response_timeout,
            )
        finally:
            self._bus.unsubscribe(SwitchPositionChanged, on_response)

    async def halt(self) -> None:
        await self._bus.publish(AutomationHalt())

    async def resume(self) -> None:
        await self._bus.publish(AutomationResume())

    def _ensure_train(self, train_name: str) -> dict[str, Any]:
        if train_name not in self._trains:
            self._trains[train_name] = {
                "train_name": train_name,
                "connected": False,
                "speed": 0,
                "battery_pct": 0,
                "voltage": 0.0,
            }
        return self._trains[train_name]

    def _ensure_hub(self, hub_name: str) -> HubState:
        if hub_name not in self._hubs:
            state = HubState.from_topology(hub_name, (), ())
            state.connected = False
            self._hubs[hub_name] = state
        return self._hubs[hub_name]

    async def _on_train_connected(self, event: TrainConnected) -> None:
        self._ensure_train(event.train_name)["connected"] = True

    async def _on_train_disconnected(self, event: TrainDisconnected) -> None:
        self._ensure_train(event.train_name)["connected"] = False

    async def _on_train_speed_changed(self, event: TrainSpeedChanged) -> None:
        if event.success:
            self._ensure_train(event.train_name)["speed"] = event.speed

    async def _on_train_status(self, event: TrainStatus) -> None:
        state = self._ensure_train(event.train_name)
        state["battery_pct"] = event.battery_pct
        state["voltage"] = event.voltage

    async def _on_hub_connected(self, event: HubConnected) -> None:
        self._hubs[event.hub_name] = HubState.from_topology(
            event.hub_name,
            event.switches,
            event.detectors,
            dict(event.active_trains),
        )

    async def _on_hub_disconnected(self, event: HubDisconnected) -> None:
        self._ensure_hub(event.hub_name).connected = False

    async def _on_switch_changed(self, event: SwitchPositionChanged) -> None:
        if event.ok:
            self._ensure_hub(event.hub_name).set_switch_angle(
                event.switch_name,
                event.angle,
            )

    async def _on_tag_detected(self, event: TagDetected) -> None:
        self._ensure_hub(event.hub_name).detect_train(
            event.detector_name,
            event.train_id,
        )

    async def _on_tag_removed(self, event: TagRemoved) -> None:
        self._ensure_hub(event.hub_name).remove_train(
            event.detector_name,
            event.train_id,
        )
