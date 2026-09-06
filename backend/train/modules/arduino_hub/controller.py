from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from train.core.event_bus import EventBus
from train.domain import (
    HubConnected,
    HubDisconnected,
    ArduinoHubState,
    SetSwitchPosition,
    SwitchPositionChanged,
    TagDetected,
    TagRemoved,
    TrainTagRegistry,
    UnknownTagDetected,
    UnknownTagRemoved,
)
from train.modules.arduino_hub.protocol import (
    Hello,
    ConfigRejected,
    ConfigRequest,
    InboundMessage,
    MoveAcknowledged,
    Pong,
    TagChanged,
)


class HubClient(Protocol):
    hub_name: str | None
    phase: str
    device_id: str | None
    configuration_hub: str | None
    configuration_revision: str | None
    configuration_payload: dict[str, object] | None

    def bind(self, hub_name: str) -> None: ...

    async def move_switch(
        self,
        switch_name: str,
        angle: int,
        request_id: str,
    ) -> None: ...

    async def configure(
        self,
        device_id: str,
        hub_name: str,
        config: dict[str, object],
    ) -> str: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class TagPresence:
    train_id: str | None = None
    tag_id: str | None = None


@dataclass(frozen=True, slots=True)
class PresenceChange:
    detector_name: str
    presence: TagPresence
    detected: bool


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
        self._device_config = {
            str(config["device_id"]): (hub_name, dict(config))
            for hub_name, config in hub_config.items()
            if "device_id" in config
        }
        self._clients: dict[str, HubClient] = {}
        self._registration_locks: dict[str, asyncio.Lock] = {
            hub_name: asyncio.Lock() for hub_name in hub_config
        }
        self._log = logging.getLogger("train.hub.controller")

    @property
    def clients(self) -> dict[str, HubClient]:
        return self._clients

    def get_hub_info(self, hub_name: str) -> dict[str, Any] | None:
        state = self._bus.state.arduino_hubs.get(hub_name)
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
        if isinstance(message, ConfigRequest):
            return await self._configure(client, message)
        if isinstance(message, ConfigRejected):
            if (
                client.phase != "config_sent"
                or message.device_id != client.device_id
            ):
                self._log.warning(
                    "Rejecting unexpected configuration rejection from %s",
                    message.device_id,
                )
                return False
            self._log.error(
                "Device %s rejected configuration: %s",
                message.device_id,
                message.reason,
            )
            return False
        if isinstance(message, Hello):
            return await self._register(client, message)
        if client.phase != "registered" or client.hub_name is None:
            return isinstance(message, Pong)
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
        self._log.info("Hub %s disconnected", hub_name)
        await self._bus.publish(HubDisconnected(hub_name=hub_name))

    async def set_switch(self, event: SetSwitchPosition) -> None:
        requested_angle = self._resolve_switch_angle(event)
        client = self._clients.get(event.hub_name)
        if client is None or requested_angle is None:
            await self._publish_switch_result(event, requested_angle or 0, ok=False)
            return
        try:
            await client.move_switch(
                event.switch_name,
                requested_angle,
                event.request_id,
            )
        except Exception:
            self._log.error("Failed to send command to %s", event.hub_name, exc_info=True)
            await self._publish_switch_result(event, requested_angle, ok=False)

    async def _register(self, client: HubClient, hello: Hello) -> bool:
        lock = self._registration_locks.get(hello.hub_name)
        if lock is None:
            self._log.warning("Rejecting unknown hub: %s", hello.hub_name)
            return False
        async with lock:
            return await self._register_serialized(client, hello)

    async def _configure(
        self, client: HubClient, request: ConfigRequest
    ) -> bool:
        if client.phase != "new":
            self._log.warning("Rejecting repeated configuration request")
            return False
        resolved = self._device_config.get(request.device_id)
        if resolved is None:
            self._log.warning("Rejecting unknown device: %s", request.device_id)
            return False
        hub_name, config = resolved
        try:
            await client.configure(request.device_id, hub_name, config)
        except (ConnectionError, OSError, ValueError):
            self._log.warning(
                "Failed to configure device %s", request.device_id, exc_info=True
            )
            return False
        self._log.info("Sent configuration for %s (%s)", request.device_id, hub_name)
        return True

    async def _register_serialized(
        self, client: HubClient, hello: Hello
    ) -> bool:
        if client.phase == "config_sent":
            if (
                hello.revision != client.configuration_revision
                or hello.hub_name != client.configuration_hub
                or hello.applied != client.configuration_payload
            ):
                self._log.warning("Rejecting mismatched configuration acknowledgement")
                return False
        elif client.phase == "new":
            if hello.revision is not None:
                self._log.warning("Rejecting unsolicited revision-bound hello")
                return False
            configured = self._hub_config.get(hello.hub_name)
            if configured is None or not configured.get("allow_legacy_hello", True):
                self._log.warning("Rejecting disabled legacy hello")
                return False
            current = self._clients.get(hello.hub_name)
            if current is not None and current.configuration_revision is not None:
                self._log.warning(
                    "Rejecting legacy takeover of provisioned hub %s",
                    hello.hub_name,
                )
                return False
            self._log.warning(
                "Accepting legacy hello from %s without revision binding",
                hello.hub_name,
            )
        elif client.phase == "registered":
            if (
                hello.hub_name != client.hub_name
                or hello.revision != client.configuration_revision
                or (
                    client.configuration_revision is not None
                    and hello.applied != client.configuration_payload
                )
            ):
                self._log.warning("Rejecting changed hello on registered connection")
                return False
        else:
            return False
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

        previous_state = self._bus.state.arduino_hubs.get(hello.hub_name)
        previous = _active_tags(previous_state)
        current = self._resolve_tag_snapshot(hello)
        client.bind(hello.hub_name)
        old_client = self._clients.get(hello.hub_name)
        self._clients[hello.hub_name] = client
        if old_client is not None and old_client is not client:
            old_client.close()

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
            active_trains=tuple(
                (detector_name, presence.train_id)
                for detector_name, presence in current.items()
                if presence.train_id is not None
            ),
            active_unknown_tags=tuple(
                (detector_name, presence.tag_id)
                for detector_name, presence in current.items()
                if presence.tag_id is not None
            ),
        ))
        await self._publish_snapshot_changes(hello.hub_name, previous, current)
        return True

    async def _handle_tag_change(self, hub_name: str, message: TagChanged) -> None:
        state = self._bus.state.arduino_hubs.get(hub_name)
        if (
            state is None
            or message.detector_name not in state.detectors
            or not state.detectors[message.detector_name].available
        ):
            self._log.warning(
                "Ignoring tag event from unavailable detector %s/%s",
                hub_name,
                message.detector_name,
            )
            return
        tag_id = TrainTagRegistry.normalize(message.tag_id)
        train_id = self._train_tags.resolve(tag_id)
        presence = TagPresence(
            train_id=train_id,
            tag_id=None if train_id is not None else tag_id,
        )
        active = _active_tags(state).get(message.detector_name)
        changes: tuple[PresenceChange, ...]
        if message.detected:
            if active == presence:
                changes = ()
            else:
                pending: list[PresenceChange] = []
                if active is not None:
                    pending.append(PresenceChange(
                        message.detector_name, active, False
                    ))
                pending.append(PresenceChange(
                    message.detector_name, presence, True
                ))
                changes = tuple(pending)
        elif active == presence:
            changes = (PresenceChange(
                message.detector_name, presence, False
            ),)
        else:
            changes = ()
        await self._publish_tag_changes(hub_name, changes)

    async def _handle_move_ack(
        self,
        hub_name: str,
        message: MoveAcknowledged,
    ) -> None:
        await self._bus.publish(SwitchPositionChanged(
            hub_name=hub_name,
            switch_name=message.switch_name,
            angle=message.angle,
            ok=message.ok,
            request_id=message.request_id,
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
        hub = self._hub_config.get(event.hub_name)
        if hub is None:
            return None
        switch = hub["switches"].get(event.switch_name)
        if switch is None:
            return None
        if (
            isinstance(event.target, int)
            and not isinstance(event.target, bool)
            and 0 <= event.target <= 180
        ):
            return event.target
        angle = switch.get(event.target)
        return angle if isinstance(angle, int) and not isinstance(angle, bool) else None

    def _resolve_tag_snapshot(self, hello: Hello) -> dict[str, TagPresence]:
        resolved: dict[str, TagPresence] = {}
        for tag in hello.detected_tags:
            if tag.detector_name not in hello.detectors:
                self._log.warning(
                    "Ignoring tag snapshot from unavailable detector %s/%s: %s",
                    hello.hub_name,
                    tag.detector_name,
                    TrainTagRegistry.normalize(tag.tag_id),
                )
                continue
            tag_id = TrainTagRegistry.normalize(tag.tag_id)
            train_id = self._train_tags.resolve(tag_id)
            resolved[tag.detector_name] = TagPresence(
                train_id=train_id,
                tag_id=None if train_id is not None else tag_id,
            )
        return resolved

    async def _publish_snapshot_changes(
        self,
        hub_name: str,
        previous: dict[str, TagPresence],
        current: dict[str, TagPresence],
    ) -> None:
        changes: list[PresenceChange] = []
        for detector_name, presence in previous.items():
            if current.get(detector_name) != presence:
                changes.append(PresenceChange(detector_name, presence, False))
        for detector_name, presence in current.items():
            if previous.get(detector_name) != presence:
                changes.append(PresenceChange(detector_name, presence, True))
        await self._publish_tag_changes(hub_name, changes)

    async def _publish_tag_changes(
        self,
        hub_name: str,
        changes: tuple[PresenceChange, ...] | list[PresenceChange],
    ) -> None:
        for change in changes:
            if change.presence.train_id is not None and change.detected:
                await self._bus.publish(TagDetected(
                    hub_name=hub_name,
                    detector_name=change.detector_name,
                    train_id=change.presence.train_id,
                ))
            elif change.presence.train_id is not None:
                await self._bus.publish(TagRemoved(
                    hub_name=hub_name,
                    detector_name=change.detector_name,
                    train_id=change.presence.train_id,
                ))
            elif change.presence.tag_id is not None and change.detected:
                await self._bus.publish(UnknownTagDetected(
                    hub_name=hub_name,
                    detector_name=change.detector_name,
                    tag_id=change.presence.tag_id,
                ))
            elif change.presence.tag_id is not None:
                await self._bus.publish(UnknownTagRemoved(
                    hub_name=hub_name,
                    detector_name=change.detector_name,
                    tag_id=change.presence.tag_id,
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
            request_id=event.request_id,
        ))


def _active_tags(state: ArduinoHubState | None) -> dict[str, TagPresence]:
    if state is None:
        return {}
    return {
        detector_id: TagPresence(
            train_id=detector.train_id,
            tag_id=detector.unknown_tag_id,
        )
        for detector_id, detector in state.detectors.items()
        if detector.triggered
        and (
            detector.train_id is not None
            or detector.unknown_tag_id is not None
        )
    }


def _indexed_hub_info(state: ArduinoHubState) -> dict[str, Any]:
    return {
        "hub_name": state.hub_id,
        "connected": state.connected,
        "switches": {
            name: {"name": switch.switch_id, "angle": switch.angle}
            for name, switch in state.switches.items()
        },
        "detectors": {
            name: {
                "name": detector.detector_id,
                "triggered": detector.triggered,
                "train_id": detector.train_id,
                "unknown_tag_id": detector.unknown_tag_id,
            }
            for name, detector in state.detectors.items()
        },
    }
