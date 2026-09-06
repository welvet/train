from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from pathlib import Path

from aiohttp import web

from automation_tree import AutomationParseError

from train.configuration import ConfigurationConflict, ConfigurationError
from train.core.event_bus import CommandFailed, CommandResourceNotFound, EventBus
from train.domain import (
    Event,
    InvalidPublicEvent,
    SystemState,
    decode_public_event,
    encode_public_event,
)
from train.modules.web_api.schema import STATE_API_VERSION, openapi_document
from train.modules.web_api.static_files import PACKAGED_STATIC_ROOT, StaticFileResolver

COMMAND_TIMEOUT = 3.0
STREAM_KEEPALIVE_INTERVAL = 15.0


class WebApiServer:
    def __init__(
        self,
        bus: EventBus,
        *,
        host: str,
        port: int,
        readiness_check: Callable[[], bool],
        automation_snapshot: Callable[[], dict[str, object]] | None = None,
        automation_update: Callable[[str], Awaitable[dict[str, object]]] | None = None,
        automation_subscribe: Callable[[Callable[[], None]], None] | None = None,
        automation_unsubscribe: Callable[[Callable[[], None]], None] | None = None,
        configuration_snapshot: Callable[[], dict[str, object]] | None = None,
        configuration_update: Callable[[str], Awaitable[dict[str, object]]] | None = None,
        static_root: Path | None = None,
    ) -> None:
        self._bus = bus
        self._host = host
        self._port = port
        self._readiness_check = readiness_check
        self._automation_snapshot = automation_snapshot or _empty_automation_snapshot
        self._automation_update = automation_update
        self._automation_subscribe = automation_subscribe
        self._automation_unsubscribe = automation_unsubscribe
        self._configuration_snapshot = configuration_snapshot
        self._configuration_update = configuration_update
        self._static_files = StaticFileResolver(
            static_root if static_root is not None else PACKAGED_STATIC_ROOT
        )
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._state_changed = asyncio.Condition()
        self._closing = asyncio.Event()
        self._subscribed = False
        self._automation_change_subscribed = False
        self._automation_revision = 0

    @property
    def application(self) -> web.Application | None:
        return self._app

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/health", self._handle_health)
        app.router.add_get("/api/openapi.json", self._handle_openapi)
        app.router.add_get("/api/state", self._handle_state)
        app.router.add_get("/api/state/stream", self._handle_state_stream)
        app.router.add_post("/api/events", self._handle_event)
        app.router.add_put("/api/automation", self._handle_automation_update)
        app.router.add_get("/api/configuration", self._handle_configuration)
        app.router.add_put("/api/configuration", self._handle_configuration_update)
        app.router.add_get("/{path:.*}", self._static_files.handle)
        self._app = app
        self._runner = web.AppRunner(app)
        self._closing.clear()
        try:
            await self._runner.setup()
            self._bus.subscribe(Event, self._on_event)
            self._subscribed = True
            if self._automation_subscribe is not None:
                self._automation_subscribe(self._on_automation_changed)
                self._automation_change_subscribed = True
            site = web.TCPSite(self._runner, self._host, self._port)
            await site.start()
        except Exception:
            if self._subscribed:
                self._bus.unsubscribe(Event, self._on_event)
                self._subscribed = False
            if (
                self._automation_change_subscribed
                and self._automation_unsubscribe is not None
            ):
                self._automation_unsubscribe(self._on_automation_changed)
                self._automation_change_subscribed = False
            await self._runner.cleanup()
            self._runner = None
            self._app = None
            raise

    async def stop(self) -> None:
        self._closing.set()
        async with self._state_changed:
            self._state_changed.notify_all()
        if self._subscribed:
            self._bus.unsubscribe(Event, self._on_event)
            self._subscribed = False
        if (
            self._automation_change_subscribed
            and self._automation_unsubscribe is not None
        ):
            self._automation_unsubscribe(self._on_automation_changed)
            self._automation_change_subscribed = False
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
        return web.json_response(self._state_envelope())

    async def _handle_state_stream(self, request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(
            headers={
                "Cache-Control": "no-cache",
                "Content-Type": "text/event-stream",
                "X-Accel-Buffering": "no",
            }
        )
        await response.prepare(request)
        revision = (-1, -1)

        try:
            while not self._closing.is_set():
                state = self._bus.state
                current_revision = (state.revision, self._automation_revision)
                if current_revision != revision:
                    envelope = self._state_envelope(state)
                    payload = json.dumps(envelope, separators=(",", ":"))
                    await response.write(
                        f"event: state\ndata: {payload}\n\n".encode()
                    )
                    revision = current_revision

                async with self._state_changed:
                    try:
                        await asyncio.wait_for(
                            self._state_changed.wait_for(
                                lambda: self._closing.is_set()
                                or (
                                    self._bus.state.revision,
                                    self._automation_revision,
                                ) != revision
                            ),
                            timeout=STREAM_KEEPALIVE_INTERVAL,
                        )
                    except TimeoutError:
                        await response.write(b": keepalive\n\n")
        except asyncio.CancelledError:
            raise
        except ConnectionError:
            pass

        return response

    async def _on_event(self, event: Event) -> None:
        async with self._state_changed:
            self._state_changed.notify_all()

    def _on_automation_changed(self) -> None:
        self._automation_revision += 1
        asyncio.create_task(self._notify_state_changed())

    async def _notify_state_changed(self) -> None:
        async with self._state_changed:
            self._state_changed.notify_all()

    def _state_envelope(
        self, state: SystemState | None = None
    ) -> dict[str, object]:
        return {
            "version": STATE_API_VERSION,
            "snapshot_at": time.time(),
            "state": asdict(state if state is not None else self._bus.state),
            "automation": self._automation_snapshot(),
        }

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

    async def _handle_automation_update(self, request: web.Request) -> web.Response:
        if self._automation_update is None:
            return web.json_response(
                {"error": "automation updates are unavailable"}, status=503
            )
        try:
            automation = await self._automation_update(await request.text())
        except AutomationParseError as exc:
            return web.json_response(
                {"error": exc.message, "path": exc.path}, status=400
            )
        except (UnicodeDecodeError, ValueError):
            return web.json_response({"error": "body must be valid JSON"}, status=400)
        except OSError:
            return web.json_response(
                {"error": "could not persist automation"}, status=500
            )
        except RuntimeError as exc:
            return web.json_response({"error": str(exc)}, status=503)

        if self._automation_subscribe is None:
            self._automation_revision += 1
            await self._notify_state_changed()
        return web.json_response({"automation": automation})

    async def _handle_configuration(self, request: web.Request) -> web.Response:
        if self._configuration_snapshot is None:
            return web.json_response(
                {"error": "configuration management is unavailable"}, status=503
            )
        try:
            configuration = self._configuration_snapshot()
        except (ConfigurationError, OSError) as exc:
            return web.json_response({"error": str(exc)}, status=500)
        return web.json_response(configuration)

    async def _handle_configuration_update(
        self, request: web.Request
    ) -> web.Response:
        if self._configuration_update is None:
            return web.json_response(
                {"error": "configuration management is unavailable"}, status=503
            )
        try:
            configuration = await self._configuration_update(await request.text())
        except ConfigurationConflict as exc:
            return web.json_response(
                {"error": exc.message, "path": exc.path}, status=409
            )
        except ConfigurationError as exc:
            return web.json_response(
                {"error": exc.message, "path": exc.path}, status=400
            )
        except UnicodeDecodeError:
            return web.json_response({"error": "body must be valid JSON"}, status=400)
        except OSError:
            return web.json_response(
                {"error": "could not persist configuration"}, status=500
            )
        return web.json_response(configuration)


def _empty_automation_snapshot() -> dict[str, object]:
    return {
        "document": {"version": 1, "rules": []},
        "eligible_train_ids": [],
        "paused": False,
        "statuses": [],
    }
