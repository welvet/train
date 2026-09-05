from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from aiohttp import web

from train.core.event_bus import CommandFailed, CommandResourceNotFound, EventBus
from train.domain import (
    InvalidPublicEvent,
    decode_public_event,
    encode_public_event,
)
from train.modules.web_api.schema import STATE_API_VERSION, openapi_document
from train.modules.web_api.static_files import PACKAGED_STATIC_ROOT, StaticFileResolver

COMMAND_TIMEOUT = 3.0


class WebApiServer:
    def __init__(
        self,
        bus: EventBus,
        *,
        host: str,
        port: int,
        readiness_check: Callable[[], bool],
        static_root: Path | None = None,
    ) -> None:
        self._bus = bus
        self._host = host
        self._port = port
        self._readiness_check = readiness_check
        self._static_files = StaticFileResolver(
            static_root if static_root is not None else PACKAGED_STATIC_ROOT
        )
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None

    @property
    def application(self) -> web.Application | None:
        return self._app

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/health", self._handle_health)
        app.router.add_get("/api/openapi.json", self._handle_openapi)
        app.router.add_get("/api/state", self._handle_state)
        app.router.add_post("/api/events", self._handle_event)
        app.router.add_get("/{path:.*}", self._static_files.handle)
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

    async def stop(self) -> None:
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

    async def _handle_state(self, request: web.Request) -> web.Response:
        return web.json_response({
            "version": STATE_API_VERSION,
            "state": asdict(self._bus.state),
        })

    async def _handle_openapi(self, request: web.Request) -> web.Response:
        return web.json_response(openapi_document())

    async def _handle_event(self, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
            event = decode_public_event(payload)
        except InvalidPublicEvent as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except (ValueError, TypeError):
            return web.json_response({"error": "body must be valid JSON"}, status=400)

        try:
            await self._bus.dispatch(event, timeout=COMMAND_TIMEOUT)
        except CommandResourceNotFound as exc:
            return web.json_response({"error": str(exc)}, status=404)
        except CommandFailed as exc:
            return web.json_response(
                {
                    "error": str(exc),
                    "command": encode_public_event(event),
                },
                status=409,
            )
        except TimeoutError:
            return web.json_response(
                {
                    "error": "command timed out",
                    "command": encode_public_event(event),
                },
                status=504,
            )
        return web.json_response(
            {"command": encode_public_event(event), "completed": True}
        )
