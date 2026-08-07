from __future__ import annotations

import asyncio
import collections
import logging
from typing import Any

from aiohttp import web

from train.core.event_bus import EventBus
from train.core.events.hub import (
    DetectorChanged,
    HubConnected,
    HubDisconnected,
    SetSwitchPosition,
    SwitchPositionChanged,
)
from train.core.events.train import (
    SetTrainSpeed,
    TrainConnected,
    TrainDisconnected,
    TrainSpeedChanged,
    TrainStatus,
)
from train.core.module import Module

RESPONSE_TIMEOUT = 2.0
LOG_BUFFER_SIZE = 200


class _BroadcastHandler(logging.Handler):
    def __init__(
        self,
        queues: list[asyncio.Queue[str]],
        buffer: collections.deque[str],
    ) -> None:
        super().__init__()
        self._queues = queues
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        line = self.format(record)
        self._buffer.append(line)
        for q in list(self._queues):
            try:
                q.put_nowait(line)
            except asyncio.QueueFull:
                pass


class WebApiModule(Module):
    def __init__(
        self,
        bus: EventBus,
        *,
        host: str = "0.0.0.0",
        port: int = 8080,
        shutdown_callback: Any = None,
    ) -> None:
        super().__init__(bus)
        self._host = host
        self._port = port
        self._shutdown_callback = shutdown_callback
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._log = logging.getLogger("train.web")
        self._state: dict[str, dict[str, Any]] = {}
        self._hub_state: dict[str, dict[str, Any]] = {}
        self._log_subscribers: list[asyncio.Queue[str]] = []
        self._log_buffer: collections.deque[str] = collections.deque(maxlen=LOG_BUFFER_SIZE)
        self._log_handler: _BroadcastHandler | None = None

    async def start(self) -> None:
        self.bus.subscribe(TrainConnected, self._on_connected)
        self.bus.subscribe(TrainDisconnected, self._on_disconnected)
        self.bus.subscribe(TrainSpeedChanged, self._on_speed_changed)
        self.bus.subscribe(TrainStatus, self._on_status)
        self.bus.subscribe(HubConnected, self._on_hub_connected)
        self.bus.subscribe(HubDisconnected, self._on_hub_disconnected)
        self.bus.subscribe(SwitchPositionChanged, self._on_switch_changed)
        self.bus.subscribe(DetectorChanged, self._on_detector_changed)

        self._app = web.Application()
        self._app.router.add_get("/trains/{train_name}", self._handle_get_train)
        self._app.router.add_post("/trains/{train_name}/speed", self._handle_set_speed)
        self._app.router.add_get("/hubs/{hub_name}", self._handle_get_hub)
        self._app.router.add_post(
            "/hubs/{hub_name}/switches/{switch_name}/position",
            self._handle_set_switch_position,
        )
        self._app.router.add_post("/stop", self._handle_stop)
        self._app.router.add_get("/logs", self._handle_logs)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()

        self._log_handler = _BroadcastHandler(self._log_subscribers, self._log_buffer)
        self._log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logging.getLogger().addHandler(self._log_handler)

        self._log.info("Listening on http://%s:%d", self._host, self._port)

    async def stop(self) -> None:
        if self._log_handler is not None:
            logging.getLogger().removeHandler(self._log_handler)
        if self._runner is not None:
            await self._runner.cleanup()

    def _get_train(self, train_name: str) -> dict[str, Any]:
        if train_name not in self._state:
            self._state[train_name] = {
                "train_name": train_name,
                "connected": False,
                "speed": 0,
                "battery_pct": 0,
                "voltage": 0.0,
            }
        return self._state[train_name]

    async def _on_connected(self, event: TrainConnected) -> None:
        self._get_train(event.train_name)["connected"] = True

    async def _on_disconnected(self, event: TrainDisconnected) -> None:
        self._get_train(event.train_name)["connected"] = False

    async def _on_speed_changed(self, event: TrainSpeedChanged) -> None:
        if event.success:
            self._get_train(event.train_name)["speed"] = event.speed

    async def _on_status(self, event: TrainStatus) -> None:
        state = self._get_train(event.train_name)
        state["battery_pct"] = event.battery_pct
        state["voltage"] = event.voltage

    async def _handle_get_train(self, request: web.Request) -> web.Response:
        train_name = request.match_info["train_name"]
        if train_name not in self._state:
            return web.json_response({"error": "unknown train"}, status=404)
        return web.json_response(self._state[train_name])

    async def _handle_set_speed(self, request: web.Request) -> web.Response:
        train_name = request.match_info["train_name"]

        try:
            body = await request.json()
            speed = int(body["speed"])
        except (KeyError, ValueError, TypeError):
            return web.json_response({"error": "body must be {\"speed\": <int>}"}, status=400)

        if not -100 <= speed <= 100:
            return web.json_response({"error": "speed must be between -100 and 100"}, status=400)

        future: asyncio.Future[TrainSpeedChanged] = asyncio.get_running_loop().create_future()

        async def _on_response(event: TrainSpeedChanged) -> None:
            if event.train_name == train_name and not future.done():
                future.set_result(event)

        self.bus.subscribe(TrainSpeedChanged, _on_response)
        try:
            await self.bus.publish(SetTrainSpeed(train_name=train_name, speed=speed))
            result = await asyncio.wait_for(future, timeout=RESPONSE_TIMEOUT)
            return web.json_response({
                "train_name": result.train_name,
                "speed": result.speed,
                "success": result.success,
            })
        except asyncio.TimeoutError:
            return web.json_response({"error": "timeout waiting for train response"}, status=504)
        finally:
            self.bus.unsubscribe(TrainSpeedChanged, _on_response)

    # --- Hub state ---

    def _get_hub(self, hub_name: str) -> dict[str, Any]:
        if hub_name not in self._hub_state:
            self._hub_state[hub_name] = {
                "hub_name": hub_name,
                "connected": False,
                "switches": [],
                "detectors": [],
            }
        return self._hub_state[hub_name]

    async def _on_hub_connected(self, event: HubConnected) -> None:
        state = self._get_hub(event.hub_name)
        state["connected"] = True
        state["switches"] = [{"name": s, "angle": 0} for s in event.switches]
        state["detectors"] = [{"name": d, "triggered": False} for d in event.detectors]

    async def _on_hub_disconnected(self, event: HubDisconnected) -> None:
        self._get_hub(event.hub_name)["connected"] = False

    async def _on_switch_changed(self, event: SwitchPositionChanged) -> None:
        if not event.ok:
            return
        state = self._get_hub(event.hub_name)
        for sw in state["switches"]:
            if sw["name"] == event.switch_name:
                sw["angle"] = event.angle
                break

    async def _on_detector_changed(self, event: DetectorChanged) -> None:
        state = self._get_hub(event.hub_name)
        for det in state["detectors"]:
            if det["name"] == event.detector_name:
                det["triggered"] = event.triggered
                break

    async def _handle_get_hub(self, request: web.Request) -> web.Response:
        hub_name = request.match_info["hub_name"]
        if hub_name not in self._hub_state:
            return web.json_response({"error": "unknown hub"}, status=404)
        return web.json_response(self._hub_state[hub_name])

    async def _handle_set_switch_position(self, request: web.Request) -> web.Response:
        hub_name = request.match_info["hub_name"]
        switch_name = request.match_info["switch_name"]

        try:
            body = await request.json()
            angle = int(body["angle"])
        except (KeyError, ValueError, TypeError):
            return web.json_response({"error": "body must be {\"angle\": <int>}"}, status=400)

        future: asyncio.Future[SwitchPositionChanged] = asyncio.get_running_loop().create_future()

        async def _on_response(event: SwitchPositionChanged) -> None:
            if event.hub_name == hub_name and event.switch_name == switch_name and not future.done():
                future.set_result(event)

        self.bus.subscribe(SwitchPositionChanged, _on_response)
        try:
            await self.bus.publish(SetSwitchPosition(
                hub_name=hub_name, switch_name=switch_name, angle=angle,
            ))
            result = await asyncio.wait_for(future, timeout=RESPONSE_TIMEOUT)
            return web.json_response({
                "hub_name": result.hub_name,
                "switch_name": result.switch_name,
                "angle": result.angle,
                "ok": result.ok,
            })
        except asyncio.TimeoutError:
            return web.json_response({"error": "timeout waiting for hub response"}, status=504)
        finally:
            self.bus.unsubscribe(SwitchPositionChanged, _on_response)

    async def _handle_stop(self, request: web.Request) -> web.Response:
        if self._shutdown_callback is None:
            return web.json_response({"error": "shutdown not available"}, status=503)
        self._log.info("Stop requested via API")
        self._shutdown_callback()
        return web.json_response({"ok": True})

    async def _handle_logs(self, request: web.Request) -> web.StreamResponse:
        resp = web.StreamResponse()
        resp.content_type = "text/plain"
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        await resp.prepare(request)

        for line in self._log_buffer:
            await resp.write(f"{line}\n".encode())

        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=500)
        self._log_subscribers.append(queue)
        try:
            while True:
                line = await queue.get()
                await resp.write(f"{line}\n".encode())
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            self._log_subscribers.remove(queue)
        return resp
