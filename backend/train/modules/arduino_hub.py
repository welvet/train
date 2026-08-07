from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from typing import Any

from train.core.event_bus import EventBus
from train.core.events.hub import (
    DetectorChanged,
    HubConnected,
    HubDisconnected,
    SetSwitchPosition,
    SwitchPositionChanged,
)
from train.core.module import Module


class ArduinoHubModule(Module):
    def __init__(self, bus: EventBus, *, host: str = "0.0.0.0", port: int = 9000) -> None:
        super().__init__(bus)
        self._host = host
        self._port = port
        self._server: asyncio.Server | None = None
        self._clients: dict[str, asyncio.StreamWriter] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._pending_tasks: set[asyncio.Task[None]] = set()
        self._hub_info: dict[str, dict[str, Any]] = {}
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
                        "detectors": {d: {"name": d, "triggered": False} for d in detectors},
                    }
                    self._log.info("Hub %s registered: switches=%s detectors=%s", hub_name, switches, detectors)
                    await self.bus.publish(HubConnected(hub_name=hub_name, switches=switches, detectors=detectors))

                elif event == "detector" and hub_name:
                    name = msg.get("name", "")
                    triggered = msg.get("triggered", False)
                    info = self._hub_info.get(hub_name)
                    if info and name in info["detectors"]:
                        info["detectors"][name]["triggered"] = triggered
                    await self.bus.publish(DetectorChanged(hub_name=hub_name, detector_name=name, triggered=triggered))

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

        if hub_name:
            self._clients.pop(hub_name, None)
            info = self._hub_info.get(hub_name)
            if info:
                info["connected"] = False
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
