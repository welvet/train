from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Protocol

from train.core.event_bus import EventBus
from train.domain import (
    HubConnected,
    HubDisconnected,
    HubState,
    SetSwitchPosition,
    SwitchPositionChanged,
    TagDetected,
    TagRemoved,
    TrainPresenceChange,
    TrainTagRegistry,
)
from train.modules.arduino_hub.protocol import (
    Hello,
    InboundMessage,
    MoveAcknowledged,
    Pong,
    TagChanged,
)


class HubClient(Protocol):
    hub_name: str | None

    def bind(self, hub_name: str) -> None: ...

    async def move_switch(self, switch_name: str, angle: int) -> None: ...

    def close(self) -> None: ...


class ArduinoHubController:
    def __init__(
        self,
        bus: EventBus,
        *,
        train_tags: TrainTagRegistry,
        hub_config: Mapping[str, Mapping[str, Any]],
    ) -> None:
        self._bus = bus
        self._train_tags = train_tags
        self._hub_config = hub_config
        self._clients: dict[str, HubClient] = {}
        self._hubs: dict[str, HubState] = {}
        self._log = logging.getLogger("train.hub.controller")

    @property
    def clients(self) -> dict[str, HubClient]:
        return self._clients

    def get_hub_info(self, hub_name: str) -> dict[str, Any] | None:
        state = self._hubs.get(hub_name)
        return _indexed_hub_info(state) if state is not None else None

    async def handle_message(
        self,
        client: HubClient,
        message: InboundMessage,
    ) -> bool:
        if (
            client.hub_name is not None
            and self._clients.get(client.hub_name) is not client
        ):
            self._log.warning(
                "Ignoring message from superseded connection for %s",
                client.hub_name,
            )
            return False
        if isinstance(message, Hello):
            return await self._register(client, message)
        if client.hub_name is None:
            return True
        if isinstance(message, TagChanged):
            await self._handle_tag_change(client.hub_name, message)
        elif isinstance(message, MoveAcknowledged):
            await self._handle_move_ack(client.hub_name, message)
        elif isinstance(message, Pong):
            self._log.debug("Pong from %s", client.hub_name)
        return True

    async def disconnect(self, client: HubClient) -> None:
        hub_name = client.hub_name
        if hub_name is None or self._clients.get(hub_name) is not client:
            return
        self._clients.pop(hub_name, None)
        state = self._hubs.get(hub_name)
        if state is not None:
            state.connected = False
        self._log.info("Hub %s disconnected", hub_name)
        await self._bus.publish(HubDisconnected(hub_name=hub_name))

    async def set_switch(self, event: SetSwitchPosition) -> None:
        requested_angle = self._resolve_switch_angle(event)
        client = self._clients.get(event.hub_name)
        if client is None or requested_angle is None:
            await self._publish_switch_result(event, requested_angle or 0, ok=False)
            return
        try:
            await client.move_switch(event.switch_name, requested_angle)
        except Exception:
            self._log.error("Failed to send command to %s", event.hub_name, exc_info=True)
            await self._publish_switch_result(event, requested_angle, ok=False)

    async def _register(self, client: HubClient, hello: Hello) -> bool:
        if client.hub_name is not None and client.hub_name != hello.hub_name:
            self._log.warning(
                "Rejecting hub identity change from %s to %s",
                client.hub_name,
                hello.hub_name,
            )
            return False
        if not self._matches_config(hello):
            self._log.warning(
                "Rejecting unconfigured hub topology: %s",
                hello.hub_name,
            )
            return False

        previous_state = self._hubs.get(hello.hub_name)
        previous = previous_state.active_trains if previous_state is not None else {}
        current = self._resolve_tag_snapshot(hello)
        client.bind(hello.hub_name)
        old_client = self._clients.get(hello.hub_name)
        self._clients[hello.hub_name] = client
        if old_client is not None and old_client is not client:
            old_client.close()

        self._hubs[hello.hub_name] = HubState.from_topology(
            hello.hub_name,
            hello.switches,
            hello.detectors,
            current,
        )
        self._log.info(
            "Hub %s registered: switches=%s detectors=%s",
            hello.hub_name,
            hello.switches,
            hello.detectors,
        )
        await self._bus.publish(HubConnected(
            hub_name=hello.hub_name,
            switches=hello.switches,
            detectors=hello.detectors,
            active_trains=tuple(current.items()),
        ))
        await self._publish_snapshot_changes(hello.hub_name, previous, current)
        return True

    async def _handle_tag_change(self, hub_name: str, message: TagChanged) -> None:
        train_id = self._train_tags.resolve(message.tag_id)
        if train_id is None:
            self._log.warning(
                "Ignoring unknown train tag %s from %s/%s",
                TrainTagRegistry.normalize(message.tag_id),
                hub_name,
                message.detector_name,
            )
            return
        state = self._hubs.get(hub_name)
        if state is None or message.detector_name not in state.detectors:
            self._log.warning(
                "Ignoring tag event from unknown detector %s/%s",
                hub_name,
                message.detector_name,
            )
            return
        changes = (
            state.detect_train(message.detector_name, train_id)
            if message.detected
            else state.remove_train(message.detector_name, train_id)
        )
        await self._publish_tag_changes(hub_name, changes)

    async def _handle_move_ack(
        self,
        hub_name: str,
        message: MoveAcknowledged,
    ) -> None:
        state = self._hubs.get(hub_name)
        if message.ok and state is not None and message.switch_name in state.switches:
            state.set_switch_angle(message.switch_name, message.angle)
        await self._bus.publish(SwitchPositionChanged(
            hub_name=hub_name,
            switch_name=message.switch_name,
            angle=message.angle,
            ok=message.ok,
        ))

    def _matches_config(self, hello: Hello) -> bool:
        configured = self._hub_config.get(hello.hub_name)
        if configured is None:
            return False
        return (
            set(hello.switches) == set(configured["switches"])
            and set(hello.detectors) <= set(configured["detectors"])
        )

    def _resolve_switch_angle(self, event: SetSwitchPosition) -> int | None:
        if isinstance(event.target, int) and not isinstance(event.target, bool):
            return event.target
        hub = self._hub_config.get(event.hub_name)
        if hub is None:
            return None
        switch = hub["switches"].get(event.switch_name)
        if switch is None:
            return None
        angle = switch.get(event.target)
        return angle if isinstance(angle, int) and not isinstance(angle, bool) else None

    def _resolve_tag_snapshot(self, hello: Hello) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for tag in hello.detected_tags:
            train_id = self._train_tags.resolve(tag.tag_id)
            if tag.detector_name in hello.detectors and train_id is not None:
                resolved[tag.detector_name] = train_id
            else:
                self._log.warning(
                    "Ignoring invalid train tag snapshot %s from %s/%s",
                    TrainTagRegistry.normalize(tag.tag_id),
                    hello.hub_name,
                    tag.detector_name,
                )
        return resolved

    async def _publish_snapshot_changes(
        self,
        hub_name: str,
        previous: dict[str, str],
        current: dict[str, str],
    ) -> None:
        changes: list[TrainPresenceChange] = []
        for detector_name, train_id in previous.items():
            if current.get(detector_name) != train_id:
                changes.append(TrainPresenceChange(detector_name, train_id, False))
        for detector_name, train_id in current.items():
            if previous.get(detector_name) != train_id:
                changes.append(TrainPresenceChange(detector_name, train_id, True))
        await self._publish_tag_changes(hub_name, changes)

    async def _publish_tag_changes(
        self,
        hub_name: str,
        changes: tuple[TrainPresenceChange, ...] | list[TrainPresenceChange],
    ) -> None:
        for change in changes:
            if change.detected:
                await self._bus.publish(TagDetected(
                    hub_name=hub_name,
                    detector_name=change.detector_name,
                    train_id=change.train_id,
                ))
            else:
                await self._bus.publish(TagRemoved(
                    hub_name=hub_name,
                    detector_name=change.detector_name,
                    train_id=change.train_id,
                ))

    async def _publish_switch_result(
        self,
        event: SetSwitchPosition,
        angle: int,
        *,
        ok: bool,
    ) -> None:
        await self._bus.publish(SwitchPositionChanged(
            hub_name=event.hub_name,
            switch_name=event.switch_name,
            angle=angle,
            ok=ok,
        ))


def _indexed_hub_info(state: HubState) -> dict[str, Any]:
    return {
        "hub_name": state.hub_name,
        "connected": state.connected,
        "switches": {
            name: {"name": switch.name, "angle": switch.angle}
            for name, switch in state.switches.items()
        },
        "detectors": {
            name: {
                "name": detector.name,
                "triggered": detector.triggered,
                "train_id": detector.train_id,
            }
            for name, detector in state.detectors.items()
        },
    }
