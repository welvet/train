from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from train.modules.arduino_hub.protocol import (
    InboundMessage,
    MAX_FRAME_BYTES,
    encode_configuration,
    configuration_payload,
    encode_move_command,
    encode_ping_command,
    parse_message,
)
from train.modules.arduino_hub.timing import HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT

MessageHandler = Callable[["HubConnection", InboundMessage], Awaitable[bool]]
DisconnectHandler = Callable[["HubConnection"], Awaitable[None]]
CLOSE_TIMEOUT = 1.0
CONFIG_REQUEST_TIMEOUT = 5.0
CONFIGURATION_TIMEOUT = 35.0


class HubConnection:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self.reader = reader
        self._writer = writer
        self._write_lock = asyncio.Lock()
        self._last_received_at = asyncio.get_running_loop().time()
        self.hub_name: str | None = None
        self.phase = "new"
        self.device_id: str | None = None
        self.configuration_hub: str | None = None
        self.configuration_revision: str | None = None
        self.configuration_payload: dict[str, object] | None = None
        self._phase_started_at = self._last_received_at

    def bind(self, hub_name: str) -> None:
        self.hub_name = hub_name
        self.phase = "registered"
        self._phase_started_at = asyncio.get_running_loop().time()

    async def configure(
        self,
        device_id: str,
        hub_name: str,
        config: dict[str, object],
    ) -> str:
        payload, revision = encode_configuration(hub_name, config)
        await self._write(payload)
        self.device_id = device_id
        self.configuration_hub = hub_name
        self.configuration_revision = revision
        self.configuration_payload = configuration_payload(hub_name, config)
        self.phase = "config_sent"
        self._phase_started_at = asyncio.get_running_loop().time()
        return revision

    def phase_age(self) -> float:
        return asyncio.get_running_loop().time() - self._phase_started_at

    async def move_switch(
        self,
        switch_name: str,
        angle: int,
        request_id: str,
    ) -> None:
        await self._write(encode_move_command(switch_name, angle, request_id))

    async def ping(self) -> None:
        await self._write(encode_ping_command())

    def note_received(self) -> None:
        self._last_received_at = asyncio.get_running_loop().time()

    def response_age(self) -> float:
        return asyncio.get_running_loop().time() - self._last_received_at

    async def _write(self, payload: bytes) -> None:
        async with self._write_lock:
            self._writer.write(payload)
            await self._writer.drain()

    def close(self) -> None:
        self._writer.close()

    async def wait_closed(self) -> None:
        await self._writer.wait_closed()

    @property
    def peer_name(self) -> object:
        return self._writer.get_extra_info("peername")


class ArduinoHubServer:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        on_message: MessageHandler,
        on_disconnect: DisconnectHandler,
        heartbeat_interval: float = HEARTBEAT_INTERVAL,
        heartbeat_timeout: float = HEARTBEAT_TIMEOUT,
        config_request_timeout: float = CONFIG_REQUEST_TIMEOUT,
        configuration_timeout: float = CONFIGURATION_TIMEOUT,
    ) -> None:
        self._host = host
        self._port = port
        self._on_message = on_message
        self._on_disconnect = on_disconnect
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_timeout = heartbeat_timeout
        self._config_request_timeout = config_request_timeout
        self._configuration_timeout = configuration_timeout
        self._server: asyncio.Server | None = None
        self._connections: set[HubConnection] = set()
        self._tasks: set[asyncio.Task[None]] = set()
        self._log = logging.getLogger("train.hub.transport")

    @property
    def server(self) -> asyncio.Server | None:
        return self._server

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._accept_client,
            self._host,
            self._port,
            limit=MAX_FRAME_BYTES,
        )
        self._log.info("Hub server listening on %s:%d", self._host, self._port)

    async def stop(self) -> None:
        server = self._server
        if server is not None:
            server.close()
            close_clients = getattr(server, "close_clients", None)
            if close_clients is not None:
                close_clients()
        for connection in tuple(self._connections):
            connection.close()
        for task in tuple(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if server is not None:
            try:
                await asyncio.wait_for(server.wait_closed(), timeout=CLOSE_TIMEOUT)
            except TimeoutError:
                self._log.warning("Timed out waiting for the hub server to close")
        self._connections.clear()
        self._tasks.clear()
        self._server = None

    def _accept_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        connection = HubConnection(reader, writer)
        self._connections.add(connection)
        task = asyncio.create_task(self._handle_client(connection))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        self._log.info("New connection from %s", connection.peer_name)

    async def _handle_client(self, connection: HubConnection) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(connection))
        provisioning = asyncio.create_task(self._provisioning_deadline(connection))
        try:
            while line := await connection.reader.readline():
                if len(line) > MAX_FRAME_BYTES:
                    self._log.warning("Rejecting oversized hub frame")
                    break
                connection.note_received()
                message = parse_message(line)
                if message is not None and not await self._on_message(connection, message):
                    break
        except asyncio.CancelledError:
            raise
        except (ConnectionError, asyncio.LimitOverrunError, ValueError) as exc:
            self._log.debug("Hub connection closed with an error: %s", exc)
        except Exception:
            self._log.exception("Unexpected hub client error")
        finally:
            heartbeat.cancel()
            provisioning.cancel()
            await asyncio.gather(heartbeat, provisioning, return_exceptions=True)
            self._connections.discard(connection)
            try:
                await self._on_disconnect(connection)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._log.exception("Hub disconnect handler failed")
            current_task = asyncio.current_task()
            should_wait_for_close = not connection.reader.at_eof() and (
                current_task is None or not current_task.cancelling()
            )
            connection.close()
            if should_wait_for_close:
                try:
                    await asyncio.wait_for(
                        connection.wait_closed(),
                        timeout=CLOSE_TIMEOUT,
                    )
                except asyncio.CancelledError:
                    raise
                except TimeoutError:
                    self._log.debug("Timed out waiting for hub connection to close")
                except ConnectionError as exc:
                    self._log.debug("Hub connection close failed: %s", exc)
                except Exception:
                    self._log.exception("Unexpected error closing hub connection")

    async def _heartbeat(self, connection: HubConnection) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_interval)
            try:
                if connection.response_age() >= self._heartbeat_timeout:
                    self._log.warning(
                        "Hub %s timed out after %.1f seconds",
                        connection.hub_name or connection.peer_name,
                        self._heartbeat_timeout,
                    )
                    connection.close()
                    return
                await connection.ping()
            except asyncio.CancelledError:
                raise
            except (ConnectionError, OSError) as exc:
                self._log.debug("Hub heartbeat failed: %s", exc)
                connection.close()
                return
            except Exception:
                self._log.exception("Unexpected hub heartbeat error")
                connection.close()
                return

    async def _provisioning_deadline(self, connection: HubConnection) -> None:
        while connection.phase != "registered":
            timeout = (
                self._config_request_timeout
                if connection.phase == "new"
                else self._configuration_timeout
            )
            remaining = timeout - connection.phase_age()
            if remaining <= 0:
                self._log.warning(
                    "Hub provisioning timed out in phase %s", connection.phase
                )
                connection.close()
                return
            await asyncio.sleep(min(remaining, 0.25))
