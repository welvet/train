from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from typing import Any

from train.core.event_bus import EventBus
from train.core.events.hub import (
    HubConnected,
    HubDisconnected,
    SetSwitchPosition,
    SwitchPositionChanged,
    TagDetected,
    TagRemoved,
)
from train.core.module import Module


class ArduinoHubModule(Module):
    def __init__(
        self,
        bus: EventBus,
        *,
        host: str = "0.0.0.0",
        port: int = 9000,
        train_tag_map: dict[str, str] | None = None,
    ) -> None:
        super().__init__(bus)
        self._host = host
        self._port = port
        self._server: asyncio.Server | None = None
        self._clients: dict[str, asyncio.StreamWriter] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._pending_tasks: set[asyncio.Task[None]] = set()
        self._hub_info: dict[str, dict[str, Any]] = {}
        self._train_tag_map = {
            self._normalize_tag_id(tag_id): train_id
            for tag_id, train_id in (train_tag_map or {}).items()
            if tag_id
        }
        self._log = logging.getLogger("train.hub")

    async def start(self) -> None:
        self.bus.subscribe(SetSwitchPosition, self._on_set_switch)
        self._server = await asyncio.start_server(
            self._accept_client, self._host, self._port,
        )
        self._log.info("Hub server listening on %s:%d", self._host, self._port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
        all_tasks = list(self._tasks.values()) + list(self._pending_tasks)
        for task in all_tasks:
            task.cancel()
        await asyncio.gather(*all_tasks, return_exceptions=True)
        if self._server is not None:
            await self._server.wait_closed()
        self._tasks.clear()
        self._pending_tasks.clear()
        self._clients.clear()

    def _accept_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.create_task(self._handle_client(reader, writer))
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)
        addr = writer.get_extra_info("peername")
        self._log.info("New connection from %s", addr)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        hub_name: str | None = None
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                event = msg.get("event")
                if not event:
                    continue

                if event == "hello":
                    hub_name = msg.get("hub", "")
                    switches = tuple(msg.get("switches", []))
                    detectors = tuple(msg.get("detectors", []))
                    previous_info = self._hub_info.get(hub_name)
                    previous_tags = self._active_trains_by_detector(previous_info)
                    current_tags = self._resolve_tag_snapshot(
                        hub_name, detectors, msg.get("detected_tags", [])
                    )
                    old_writer = self._clients.get(hub_name)
                    if old_writer is not None:
                        with suppress(Exception):
                            old_writer.close()
                    self._clients[hub_name] = writer
                    if hub_name in self._tasks:
                        self._tasks[hub_name].cancel()
                    self._tasks[hub_name] = asyncio.current_task()  # type: ignore[assignment]
                    self._hub_info[hub_name] = {
                        "hub_name": hub_name,
                        "connected": True,
                        "switches": {s: {"name": s, "angle": 0} for s in switches},
                        "detectors": {
                            d: {
                                "name": d,
                                "triggered": d in current_tags,
                                "train_id": current_tags.get(d),
                            }
                            for d in detectors
                        },
                    }
                    self._log.info("Hub %s registered: switches=%s detectors=%s", hub_name, switches, detectors)
                    await self.bus.publish(HubConnected(
                        hub_name=hub_name,
                        switches=switches,
                        detectors=detectors,
                        active_trains=tuple(current_tags.items()),
                    ))
                    await self._publish_snapshot_changes(
                        hub_name, previous_tags, current_tags
                    )

                elif event in {"tag_detected", "tag_removed"} and hub_name:
                    name = msg.get("detector", "")
                    tag_id = self._normalize_tag_id(msg.get("tag_id", ""))
                    train_id = self._train_tag_map.get(tag_id)
                    if not train_id:
                        self._log.warning(
                            "Ignoring unknown train tag %s from %s/%s",
                            tag_id,
                            hub_name,
                            name,
                        )
                        continue

                    info = self._hub_info.get(hub_name)
                    if not info or name not in info["detectors"]:
                        self._log.warning(
                            "Ignoring tag event from unknown detector %s/%s",
                            hub_name,
                            name,
                        )
                        continue
                    await self._apply_tag_change(
                        hub_name=hub_name,
                        detector_name=name,
                        train_id=train_id,
                        detected=event == "tag_detected",
                    )

                elif event == "move_ack" and hub_name:
                    switch_name = msg.get("switch", "")
                    angle = msg.get("angle", 0)
                    ok = msg.get("ok", False)
                    if ok:
                        info = self._hub_info.get(hub_name)
                        if info and switch_name in info["switches"]:
                            info["switches"][switch_name]["angle"] = angle
                    await self.bus.publish(SwitchPositionChanged(
                        hub_name=hub_name, switch_name=switch_name, angle=angle, ok=ok,
                    ))

                elif event == "pong" and hub_name:
                    self._log.debug("Pong from %s", hub_name)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._log.warning("Client error: %s", exc)

        if hub_name and self._clients.get(hub_name) is writer:
            self._clients.pop(hub_name, None)
            info = self._hub_info.get(hub_name)
            if info:
                info["connected"] = False
            if self._tasks.get(hub_name) is asyncio.current_task():
                self._tasks.pop(hub_name, None)
            self._log.info("Hub %s disconnected", hub_name)
            with suppress(BaseException):
                await self.bus.publish(HubDisconnected(hub_name=hub_name))
        with suppress(Exception):
            writer.close()

    async def _on_set_switch(self, event: SetSwitchPosition) -> None:
        writer = self._clients.get(event.hub_name)
        if writer is None:
            await self.bus.publish(SwitchPositionChanged(
                hub_name=event.hub_name, switch_name=event.switch_name,
                angle=event.angle, ok=False,
            ))
            return
        cmd = json.dumps({"cmd": "move", "switch": event.switch_name, "angle": event.angle})
        try:
            writer.write((cmd + "\n").encode())
            await writer.drain()
        except Exception:
            self._log.error("Failed to send command to %s", event.hub_name, exc_info=True)
            await self.bus.publish(SwitchPositionChanged(
                hub_name=event.hub_name, switch_name=event.switch_name,
                angle=event.angle, ok=False,
            ))

    def get_hub_info(self, hub_name: str) -> dict[str, Any] | None:
        return self._hub_info.get(hub_name)

    @staticmethod
    def _normalize_tag_id(tag_id: object) -> str:
        return str(tag_id).strip().upper()

    @staticmethod
    def _active_trains_by_detector(
        info: dict[str, Any] | None,
    ) -> dict[str, str]:
        if not info:
            return {}
        return {
            name: detector["train_id"]
            for name, detector in info["detectors"].items()
            if detector.get("triggered") and detector.get("train_id")
        }

    def _resolve_tag_snapshot(
        self,
        hub_name: str,
        detectors: tuple[str, ...],
        detected_tags: object,
    ) -> dict[str, str]:
        if not isinstance(detected_tags, list):
            return {}

        resolved: dict[str, str] = {}
        for tag in detected_tags:
            if not isinstance(tag, dict):
                continue
            detector_name = str(tag.get("detector", ""))
            tag_id = self._normalize_tag_id(tag.get("tag_id", ""))
            train_id = self._train_tag_map.get(tag_id)
            if detector_name in detectors and train_id:
                resolved[detector_name] = train_id
            else:
                self._log.warning(
                    "Ignoring invalid train tag snapshot %s from %s/%s",
                    tag_id,
                    hub_name,
                    detector_name,
                )
        return resolved

    async def _apply_tag_change(
        self,
        *,
        hub_name: str,
        detector_name: str,
        train_id: str,
        detected: bool,
    ) -> None:
        detector = self._hub_info[hub_name]["detectors"][detector_name]
        active_train_id = detector.get("train_id") if detector.get("triggered") else None

        if detected:
            if active_train_id == train_id:
                return
            if active_train_id:
                await self.bus.publish(TagRemoved(
                    hub_name=hub_name,
                    detector_name=detector_name,
                    train_id=active_train_id,
                ))
            detector["triggered"] = True
            detector["train_id"] = train_id
            await self.bus.publish(TagDetected(
                hub_name=hub_name,
                detector_name=detector_name,
                train_id=train_id,
            ))
            return

        if active_train_id != train_id:
            return
        detector["triggered"] = False
        detector["train_id"] = None
        await self.bus.publish(TagRemoved(
            hub_name=hub_name,
            detector_name=detector_name,
            train_id=train_id,
        ))

    async def _publish_snapshot_changes(
        self,
        hub_name: str,
        previous: dict[str, str],
        current: dict[str, str],
    ) -> None:
        for detector_name, train_id in previous.items():
            if current.get(detector_name) != train_id:
                await self.bus.publish(TagRemoved(
                    hub_name=hub_name,
                    detector_name=detector_name,
                    train_id=train_id,
                ))
        for detector_name, train_id in current.items():
            if previous.get(detector_name) != train_id:
                await self.bus.publish(TagDetected(
                    hub_name=hub_name,
                    detector_name=detector_name,
                    train_id=train_id,
                ))
