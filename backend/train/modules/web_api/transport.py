from __future__ import annotations

import asyncio
import collections
import logging
import os
from collections.abc import Callable
from typing import Any

from aiohttp import web

from train.modules.web_api.controller import WebApiController
from train.modules.web_api.protocol import (
    InvalidRequest,
    hub_api_response,
    parse_speed,
    parse_switch_target,
)

LOG_BUFFER_SIZE = 200
LOG_SUBSCRIBER_QUEUE_SIZE = 500


class BroadcastLogHandler(logging.Handler):
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
        for queue in tuple(self._queues):
            try:
                queue.put_nowait(line)
            except asyncio.QueueFull:
                pass


class WebApiServer:
    def __init__(
        self,
        controller: WebApiController,
        *,
        host: str,
        port: int,
        shutdown_callback: Callable[[], Any] | None,
        readiness_check: Callable[[], bool],
    ) -> None:
        self._controller = controller
        self._host = host
        self._port = port
        self._shutdown_callback = shutdown_callback
        self._readiness_check = readiness_check
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._log = logging.getLogger("train.web")
        self._log_subscribers: list[asyncio.Queue[str]] = []
        self._log_buffer: collections.deque[str] = collections.deque(
            maxlen=LOG_BUFFER_SIZE
        )
        self._log_handler: BroadcastLogHandler | None = None

    @property
    def application(self) -> web.Application | None:
        return self._app

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/health", self._handle_health)
        app.router.add_get("/trains/{train_name}", self._handle_get_train)
        app.router.add_post("/trains/{train_name}/speed", self._handle_set_speed)
        app.router.add_get("/hubs/{hub_name}", self._handle_get_hub)
        app.router.add_post(
            "/hubs/{hub_name}/switches/{switch_name}/position",
            self._handle_set_switch_position,
        )
        app.router.add_post("/stop", self._handle_stop)
        app.router.add_post("/halt", self._handle_halt)
        app.router.add_post("/resume", self._handle_resume)
        app.router.add_get("/logs", self._handle_logs)
        self._app = app
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        try:
            site = web.TCPSite(self._runner, self._host, self._port)
            await site.start()
        except Exception:
            await self._runner.cleanup()
            self._runner = None
            self._app = None
            raise

        self._log_handler = BroadcastLogHandler(
            self._log_subscribers,
            self._log_buffer,
        )
        self._log_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logging.getLogger().addHandler(self._log_handler)
        self._log.info("Listening on http://%s:%d", self._host, self._port)

    async def stop(self) -> None:
        if self._log_handler is not None:
            logging.getLogger().removeHandler(self._log_handler)
            self._log_handler = None
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        self._app = None

    async def _handle_health(self, request: web.Request) -> web.Response:
        ready = self._readiness_check()
        return web.json_response(
            {
                "status": "ok" if ready else "error",
                "release": os.environ.get("TRAIN_RELEASE_ID", "development"),
            },
            status=200 if ready else 503,
        )

    async def _handle_get_train(self, request: web.Request) -> web.Response:
        state = self._controller.get_train(request.match_info["train_name"])
        if state is None:
            return web.json_response({"error": "unknown train"}, status=404)
        return web.json_response(state)

    async def _handle_set_speed(self, request: web.Request) -> web.Response:
        try:
            speed = parse_speed(await request.json())
        except InvalidRequest as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except (ValueError, TypeError):
            return web.json_response(
                {"error": 'body must be {"speed": <int>}'},
                status=400,
            )

        train_name = request.match_info["train_name"]
        try:
            result = await self._controller.set_train_speed(train_name, speed)
        except TimeoutError:
            return web.json_response(
                {"error": "timeout waiting for train response"},
                status=504,
            )
        return web.json_response({
            "train_name": result.train_name,
            "speed": result.speed,
            "success": result.success,
        })

    async def _handle_get_hub(self, request: web.Request) -> web.Response:
        state = self._controller.get_hub(request.match_info["hub_name"])
        if state is None:
            return web.json_response({"error": "unknown hub"}, status=404)
        return web.json_response(hub_api_response(state))

    async def _handle_set_switch_position(self, request: web.Request) -> web.Response:
        try:
            target = parse_switch_target(await request.json())
        except InvalidRequest as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except (ValueError, TypeError):
            return web.json_response({"error": "invalid JSON body"}, status=400)

        hub_name = request.match_info["hub_name"]
        switch_name = request.match_info["switch_name"]
        try:
            result = await self._controller.set_switch_position(
                hub_name,
                switch_name,
                target,
            )
        except TimeoutError:
            return web.json_response(
                {"error": "timeout waiting for hub response"},
                status=504,
            )
        return web.json_response({
            "hub_name": result.hub_name,
            "switch_name": result.switch_name,
            "angle": result.angle,
            "ok": result.ok,
        })

    async def _handle_stop(self, request: web.Request) -> web.Response:
        if self._shutdown_callback is None:
            return web.json_response({"error": "shutdown not available"}, status=503)
        self._log.info("Stop requested via API")
        self._shutdown_callback()
        return web.json_response({"ok": True})

    async def _handle_halt(self, request: web.Request) -> web.Response:
        await self._controller.halt()
        return web.json_response({"ok": True})

    async def _handle_resume(self, request: web.Request) -> web.Response:
        await self._controller.resume()
        return web.json_response({"ok": True})

    async def _handle_logs(self, request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse()
        response.content_type = "text/plain"
        response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Accel-Buffering"] = "no"
        await response.prepare(request)

        for line in self._log_buffer:
            await response.write(f"{line}\n".encode())

        queue: asyncio.Queue[str] = asyncio.Queue(
            maxsize=LOG_SUBSCRIBER_QUEUE_SIZE
        )
        self._log_subscribers.append(queue)
        try:
            while True:
                line = await queue.get()
                await response.write(f"{line}\n".encode())
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            self._log_subscribers.remove(queue)
        return response
