from __future__ import annotations

import asyncio
import json

import pytest

from train.core.event_bus import EventBus
from train.core.events import Event
from train.core.events.hub import (
    DetectorChanged,
    HubConnected,
    HubDisconnected,
    SetSwitchPosition,
    SwitchPositionChanged,
)
from train.modules.arduino_hub import ArduinoHubModule


def _collect_events(bus: EventBus) -> list[Event]:
    events: list[Event] = []

    async def _handler(event: Event) -> None:
        events.append(event)

    bus.subscribe(Event, _handler)
    return events


async def _send_line(writer: asyncio.StreamWriter, msg: dict) -> None:
    writer.write((json.dumps(msg) + "\n").encode())
    await writer.drain()


async def _read_line(reader: asyncio.StreamReader) -> dict:
    line = await asyncio.wait_for(reader.readline(), timeout=2.0)
    return json.loads(line)


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
async def hub(bus: EventBus):
    mod = ArduinoHubModule(bus, host="127.0.0.1", port=0)
    await mod.start()
    port = mod._server.sockets[0].getsockname()[1]
    yield mod, port
    await mod.stop()


async def _connect_hub(port: int, hub_name: str = "A_HUB_1"):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    await _send_line(writer, {
        "event": "hello",
        "hub": hub_name,
        "switches": ["S1", "S2"],
        "detectors": ["D1", "D2"],
    })
    await asyncio.sleep(0.05)
    return reader, writer


async def test_hello_publishes_hub_connected(bus: EventBus, hub) -> None:
    mod, port = hub
    events = _collect_events(bus)
    reader, writer = await _connect_hub(port)
    await asyncio.sleep(0.05)

    connected = [e for e in events if isinstance(e, HubConnected)]
    assert len(connected) == 1
    assert connected[0].hub_name == "A_HUB_1"
    assert connected[0].switches == ("S1", "S2")
    assert connected[0].detectors == ("D1", "D2")

    writer.close()
    await writer.wait_closed()


async def test_detector_event(bus: EventBus, hub) -> None:
    mod, port = hub
    events = _collect_events(bus)
    reader, writer = await _connect_hub(port)

    await _send_line(writer, {"event": "detector", "hub": "A_HUB_1", "name": "D1", "triggered": True})
    await asyncio.sleep(0.05)

    detector_events = [e for e in events if isinstance(e, DetectorChanged)]
    assert len(detector_events) == 1
    assert detector_events[0].detector_name == "D1"
    assert detector_events[0].triggered is True

    writer.close()
    await writer.wait_closed()


async def test_move_command_and_ack(bus: EventBus, hub) -> None:
    mod, port = hub
    events = _collect_events(bus)
    reader, writer = await _connect_hub(port)

    await bus.publish(SetSwitchPosition(hub_name="A_HUB_1", switch_name="S1", angle=100))
    cmd = await _read_line(reader)
    assert cmd["cmd"] == "move"
    assert cmd["switch"] == "S1"
    assert cmd["angle"] == 100

    await _send_line(writer, {"event": "move_ack", "hub": "A_HUB_1", "switch": "S1", "angle": 100, "ok": True})
    await asyncio.sleep(0.05)

    acks = [e for e in events if isinstance(e, SwitchPositionChanged)]
    assert len(acks) == 1
    assert acks[0].ok is True

    writer.close()
    await writer.wait_closed()


async def test_move_disconnected_hub(bus: EventBus, hub) -> None:
    mod, port = hub
    events = _collect_events(bus)

    await bus.publish(SetSwitchPosition(hub_name="A_HUB_1", switch_name="S1", angle=100))
    await asyncio.sleep(0.05)

    acks = [e for e in events if isinstance(e, SwitchPositionChanged)]
    assert len(acks) == 1
    assert acks[0].ok is False


async def test_disconnect_publishes_event(bus: EventBus, hub) -> None:
    mod, port = hub
    events = _collect_events(bus)
    reader, writer = await _connect_hub(port)
    await asyncio.sleep(0.05)

    writer.close()
    await writer.wait_closed()
    await asyncio.sleep(0.1)

    disconnected = [e for e in events if isinstance(e, HubDisconnected)]
    assert len(disconnected) == 1
    assert disconnected[0].hub_name == "A_HUB_1"


async def test_multiple_hubs(bus: EventBus, hub) -> None:
    mod, port = hub
    events = _collect_events(bus)

    r1, w1 = await _connect_hub(port, "HUB_A")
    r2, w2 = await _connect_hub(port, "HUB_B")
    await asyncio.sleep(0.05)

    connected = [e for e in events if isinstance(e, HubConnected)]
    names = {e.hub_name for e in connected}
    assert names == {"HUB_A", "HUB_B"}

    w1.close()
    await w1.wait_closed()
    w2.close()
    await w2.wait_closed()


async def test_hub_info_tracks_state(bus: EventBus, hub) -> None:
    mod, port = hub
    reader, writer = await _connect_hub(port)

    await _send_line(writer, {"event": "detector", "hub": "A_HUB_1", "name": "D1", "triggered": True})
    await asyncio.sleep(0.05)

    info = mod.get_hub_info("A_HUB_1")
    assert info is not None
    assert info["detectors"]["D1"]["triggered"] is True

    writer.close()
    await writer.wait_closed()


async def test_clean_shutdown(bus: EventBus) -> None:
    mod = ArduinoHubModule(bus, host="127.0.0.1", port=0)
    await mod.start()
    port = mod._server.sockets[0].getsockname()[1]

    reader, writer = await _connect_hub(port)
    await asyncio.sleep(0.05)
    assert len(mod._clients) == 1

    await mod.stop()
    await asyncio.sleep(0.05)
    assert len(mod._clients) == 0
