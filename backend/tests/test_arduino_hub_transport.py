from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import AsyncMock, Mock

from train.modules.arduino_hub.transport import ArduinoHubServer, HubConnection


def _server(*, heartbeat_interval: float, heartbeat_timeout: float) -> ArduinoHubServer:
    return ArduinoHubServer(
        "127.0.0.1",
        0,
        on_message=AsyncMock(return_value=True),
        on_disconnect=AsyncMock(),
        heartbeat_interval=heartbeat_interval,
        heartbeat_timeout=heartbeat_timeout,
    )


async def test_unresponsive_hub_is_disconnected_after_heartbeat_timeout() -> None:
    disconnected = asyncio.Event()

    async def handle_message(connection: HubConnection, message: object) -> bool:
        connection.bind("yard")
        return True

    async def handle_disconnect(connection: HubConnection) -> None:
        disconnected.set()

    server = ArduinoHubServer(
        "127.0.0.1",
        0,
        on_message=handle_message,
        on_disconnect=handle_disconnect,
        heartbeat_interval=0.01,
        heartbeat_timeout=0.03,
    )
    await server.start()
    assert server.server is not None
    port = server.server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(b'{"event": "pong"}\n')
    await writer.drain()

    try:
        ping = json.loads(await asyncio.wait_for(reader.readline(), timeout=0.1))
        assert ping == {"cmd": "ping"}
        await asyncio.wait_for(disconnected.wait(), timeout=0.2)
        while await asyncio.wait_for(reader.readline(), timeout=0.1):
            pass
        assert reader.at_eof()
    finally:
        writer.close()
        await writer.wait_closed()
        await server.stop()


async def test_heartbeat_responses_keep_hub_connected() -> None:
    disconnected = asyncio.Event()

    async def handle_message(connection: HubConnection, message: object) -> bool:
        connection.bind("yard")
        return True

    async def handle_disconnect(connection: HubConnection) -> None:
        disconnected.set()

    server = ArduinoHubServer(
        "127.0.0.1",
        0,
        on_message=handle_message,
        on_disconnect=handle_disconnect,
        heartbeat_interval=0.01,
        heartbeat_timeout=0.04,
    )
    await server.start()
    assert server.server is not None
    port = server.server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)

    try:
        for _ in range(6):
            ping = json.loads(await asyncio.wait_for(reader.readline(), timeout=0.1))
            assert ping == {"cmd": "ping"}
            writer.write(b'{"event": "pong"}\n')
            await writer.drain()
        assert not disconnected.is_set()
    finally:
        writer.close()
        await writer.wait_closed()
        await server.stop()


async def test_unexpected_heartbeat_failure_closes_connection(caplog) -> None:
    connection = Mock(spec=HubConnection)
    connection.response_age.return_value = 0
    connection.ping = AsyncMock(side_effect=RuntimeError("write failed"))
    server = _server(heartbeat_interval=0, heartbeat_timeout=1)

    with caplog.at_level(logging.ERROR, logger="train.hub.transport"):
        await server._heartbeat(connection)

    connection.close.assert_called_once_with()
    assert "Unexpected hub heartbeat error" in caplog.text


async def test_unidentified_connection_is_closed_at_provisioning_deadline() -> None:
    connection = Mock(spec=HubConnection)
    connection.phase = "new"
    connection.phase_age.return_value = 1.0
    server = ArduinoHubServer(
        "127.0.0.1",
        0,
        on_message=AsyncMock(return_value=True),
        on_disconnect=AsyncMock(),
        config_request_timeout=0.5,
    )

    await server._provisioning_deadline(connection)

    connection.close.assert_called_once_with()
