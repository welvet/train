from __future__ import annotations

import asyncio
import json

import pytest

from train.core.event_bus import EventBus
from train.domain import (
    Event,
    HubConnected,
    HubDisconnected,
    SetSwitchPosition,
    SwitchPositionChanged,
    SystemState,
    TagDetected,
    TagRemoved,
)
from train.modules.arduino_hub import ArduinoHubModule

HUB_CONFIG = {
    "A_HUB_1": {
        "switches": {
            "S1": {"straight": 58, "diverge": 100},
            "S2": {"straight": 58, "diverge": 100},
        },
        "detectors": ("D1", "D2"),
    },
    "HUB_A": {
        "switches": {
            "S1": {"straight": 58, "diverge": 100},
            "S2": {"straight": 58, "diverge": 100},
        },
        "detectors": ("D1", "D2"),
    },
    "HUB_B": {
        "switches": {
            "S1": {"straight": 58, "diverge": 100},
            "S2": {"straight": 58, "diverge": 100},
        },
        "detectors": ("D1", "D2"),
    },
}


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
    return EventBus(SystemState.from_topology(arduino_hubs=HUB_CONFIG))


@pytest.fixture
async def hub(bus: EventBus):
    mod = ArduinoHubModule(
        bus,
        host="127.0.0.1",
        port=0,
        train_tag_map={
            "04:A1:B2:C3": "arctic_express",
            "04:11:22:33": "cargo_train",
        },
        hub_config=HUB_CONFIG,
    )
    await mod.start()
    port = mod._server.sockets[0].getsockname()[1]
    yield mod, port
    await mod.stop()


async def _connect_hub(
    port: int,
    hub_name: str = "A_HUB_1",
    *,
    detected_tags: list[dict[str, str]] | None = None,
):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    await _send_line(writer, {
        "event": "hello",
        "hub": hub_name,
        "switches": ["S1", "S2"],
        "detectors": ["D1", "D2"],
        "detected_tags": detected_tags or [],
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


async def test_unconfigured_hub_is_rejected(bus: EventBus, hub) -> None:
    mod, port = hub
    events = _collect_events(bus)
    reader, writer = await _connect_hub(port, hub_name="unknown")

    assert await asyncio.wait_for(reader.read(), timeout=2.0) == b""
    assert "unknown" not in mod._clients
    assert not [event for event in events if isinstance(event, HubConnected)]

    writer.close()
    await writer.wait_closed()


async def test_mismatched_switch_topology_is_rejected(bus: EventBus, hub) -> None:
    mod, port = hub
    events = _collect_events(bus)
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    await _send_line(writer, {
        "event": "hello",
        "hub": "A_HUB_1",
        "switches": ["S1", "unexpected"],
        "detectors": ["D1"],
        "detected_tags": [],
    })

    assert await asyncio.wait_for(reader.read(), timeout=2.0) == b""
    assert "A_HUB_1" not in mod._clients
    assert not [event for event in events if isinstance(event, HubConnected)]

    writer.close()
    await writer.wait_closed()


async def test_tag_events_include_train_id(bus: EventBus, hub) -> None:
    mod, port = hub
    events = _collect_events(bus)
    reader, writer = await _connect_hub(port)

    await _send_line(writer, {
        "event": "tag_detected",
        "hub": "A_HUB_1",
        "detector": "D1",
        "tag_id": "04:a1:b2:c3",
    })
    await _send_line(writer, {
        "event": "tag_removed",
        "hub": "A_HUB_1",
        "detector": "D1",
        "tag_id": "04:A1:B2:C3",
    })
    await asyncio.sleep(0.05)

    detected = [e for e in events if isinstance(e, TagDetected)]
    removed = [e for e in events if isinstance(e, TagRemoved)]
    assert len(detected) == 1
    assert detected[0].detector_name == "D1"
    assert detected[0].train_id == "arctic_express"
    assert len(removed) == 1
    assert removed[0].train_id == "arctic_express"

    writer.close()
    await writer.wait_closed()


async def test_initial_snapshot_publishes_detected_train(bus: EventBus, hub) -> None:
    mod, port = hub
    events = _collect_events(bus)
    reader, writer = await _connect_hub(
        port,
        detected_tags=[{"detector": "D1", "tag_id": "04:a1:b2:c3"}],
    )

    connected = [event for event in events if isinstance(event, HubConnected)]
    detected = [event for event in events if isinstance(event, TagDetected)]
    assert connected[0].active_trains == (("D1", "arctic_express"),)
    assert len(detected) == 1
    assert detected[0].hub_name == "A_HUB_1"
    assert detected[0].detector_name == "D1"
    assert detected[0].train_id == "arctic_express"
    info = mod.get_hub_info("A_HUB_1")
    assert info is not None
    assert info["detectors"]["D1"]["train_id"] == "arctic_express"

    writer.close()
    await writer.wait_closed()


async def test_same_tag_reconnect_does_not_repeat_tag_events(bus: EventBus, hub) -> None:
    mod, port = hub
    events = _collect_events(bus)
    snapshot = [{"detector": "D1", "tag_id": "04:A1:B2:C3"}]
    reader1, writer1 = await _connect_hub(port, detected_tags=snapshot)
    events.clear()

    reader2, writer2 = await _connect_hub(port, detected_tags=snapshot)
    await asyncio.sleep(0.05)

    assert len([event for event in events if isinstance(event, HubConnected)]) == 1
    assert not [
        event for event in events if isinstance(event, (TagDetected, TagRemoved))
    ]
    assert not [event for event in events if isinstance(event, HubDisconnected)]
    assert await asyncio.wait_for(reader1.read(), timeout=2.0) == b""
    assert "A_HUB_1" in mod._clients
    assert mod.get_hub_info("A_HUB_1")["connected"] is True

    writer1.close()
    await writer1.wait_closed()
    writer2.close()
    await writer2.wait_closed()


async def test_reconnect_reconciles_tag_removed_while_disconnected(
    bus: EventBus, hub
) -> None:
    mod, port = hub
    events = _collect_events(bus)
    reader1, writer1 = await _connect_hub(
        port,
        detected_tags=[{"detector": "D1", "tag_id": "04:A1:B2:C3"}],
    )
    events.clear()

    reader2, writer2 = await _connect_hub(port)
    await asyncio.sleep(0.05)

    removed = [event for event in events if isinstance(event, TagRemoved)]
    assert len(removed) == 1
    assert removed[0].hub_name == "A_HUB_1"
    assert removed[0].detector_name == "D1"
    assert removed[0].train_id == "arctic_express"
    info = mod.get_hub_info("A_HUB_1")
    assert info is not None
    assert info["detectors"]["D1"] == {
        "name": "D1",
        "triggered": False,
        "train_id": None,
    }

    writer1.close()
    await writer1.wait_closed()
    writer2.close()
    await writer2.wait_closed()


async def test_unknown_tags_are_ignored(bus: EventBus, hub) -> None:
    mod, port = hub
    events = _collect_events(bus)
    reader, writer = await _connect_hub(
        port,
        detected_tags=[{"detector": "D1", "tag_id": "DE:AD:BE:EF"}],
    )
    await _send_line(writer, {
        "event": "tag_detected",
        "hub": "A_HUB_1",
        "detector": "D1",
        "tag_id": "DE:AD:BE:EF",
    })
    await asyncio.sleep(0.05)

    assert not [
        event for event in events if isinstance(event, (TagDetected, TagRemoved))
    ]
    info = mod.get_hub_info("A_HUB_1")
    assert info is not None
    assert info["detectors"]["D1"]["triggered"] is False

    writer.close()
    await writer.wait_closed()


async def test_events_from_unavailable_detector_are_ignored(
    bus: EventBus, hub
) -> None:
    mod, port = hub
    events = _collect_events(bus)
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    await _send_line(writer, {
        "event": "hello",
        "hub": "A_HUB_1",
        "switches": ["S1", "S2"],
        "detectors": ["D1"],
        "detected_tags": [],
    })
    await asyncio.sleep(0.05)
    events.clear()

    await _send_line(writer, {
        "event": "tag_detected",
        "hub": "A_HUB_1",
        "detector": "D2",
        "tag_id": "04:A1:B2:C3",
    })
    await asyncio.sleep(0.05)

    assert not [event for event in events if isinstance(event, TagDetected)]
    assert mod.get_hub_info("A_HUB_1")["detectors"]["D2"]["triggered"] is False

    writer.close()
    await writer.wait_closed()


async def test_live_tag_events_are_idempotent_and_reconcile_replacement(
    bus: EventBus, hub
) -> None:
    mod, port = hub
    events = _collect_events(bus)
    reader, writer = await _connect_hub(port)
    first_tag = {
        "event": "tag_detected",
        "hub": "A_HUB_1",
        "detector": "D1",
        "tag_id": "04:A1:B2:C3",
    }
    await _send_line(writer, first_tag)
    await _send_line(writer, first_tag)
    await _send_line(writer, {
        "event": "tag_removed",
        "hub": "A_HUB_1",
        "detector": "D1",
        "tag_id": "04:11:22:33",
    })
    await _send_line(writer, {
        "event": "tag_detected",
        "hub": "A_HUB_1",
        "detector": "D1",
        "tag_id": "04:11:22:33",
    })
    await asyncio.sleep(0.05)

    tag_events = [
        event for event in events if isinstance(event, (TagDetected, TagRemoved))
    ]
    assert [type(event) for event in tag_events] == [
        TagDetected,
        TagRemoved,
        TagDetected,
    ]
    assert [event.train_id for event in tag_events] == [
        "arctic_express",
        "arctic_express",
        "cargo_train",
    ]
    info = mod.get_hub_info("A_HUB_1")
    assert info is not None
    assert info["detectors"]["D1"]["train_id"] == "cargo_train"

    writer.close()
    await writer.wait_closed()


async def test_duplicate_hub_connection_takes_over_without_disconnect_event(
    bus: EventBus, hub
) -> None:
    mod, port = hub
    events = _collect_events(bus)
    reader1, writer1 = await _connect_hub(port)
    events.clear()

    reader2, writer2 = await _connect_hub(port)
    await asyncio.sleep(0.05)
    await _send_line(writer2, {
        "event": "tag_detected",
        "hub": "A_HUB_1",
        "detector": "D1",
        "tag_id": "04:A1:B2:C3",
    })
    await asyncio.sleep(0.05)

    await bus.publish(
        SetSwitchPosition(hub_name="A_HUB_1", switch_name="S1", target="diverge")
    )
    command = await _read_line(reader2)
    assert command["cmd"] == "move"
    assert command["angle"] == 100
    assert not [event for event in events if isinstance(event, HubDisconnected)]
    assert len([event for event in events if isinstance(event, TagDetected)]) == 1

    writer1.close()
    await writer1.wait_closed()
    writer2.close()
    await writer2.wait_closed()


async def test_duplicate_hub_registration_is_serialized(
    bus: EventBus, hub
) -> None:
    mod, port = hub
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    registrations = 0

    async def delay_first_registration(event: HubConnected) -> None:
        nonlocal registrations
        registrations += 1
        if registrations == 1:
            first_started.set()
            await release_first.wait()

    bus.subscribe(HubConnected, delay_first_registration)
    reader1, writer1 = await asyncio.open_connection("127.0.0.1", port)
    await _send_line(writer1, {
        "event": "hello",
        "hub": "A_HUB_1",
        "switches": ["S1", "S2"],
        "detectors": ["D1", "D2"],
        "detected_tags": [
            {"detector": "D1", "tag_id": "04:A1:B2:C3"}
        ],
    })
    await asyncio.wait_for(first_started.wait(), timeout=2.0)

    reader2, writer2 = await asyncio.open_connection("127.0.0.1", port)
    await _send_line(writer2, {
        "event": "hello",
        "hub": "A_HUB_1",
        "switches": ["S1", "S2"],
        "detectors": ["D1", "D2"],
        "detected_tags": [
            {"detector": "D1", "tag_id": "04:11:22:33"}
        ],
    })
    await asyncio.sleep(0.05)

    assert registrations == 1
    release_first.set()
    await asyncio.sleep(0.1)

    assert registrations == 2
    assert mod.get_hub_info("A_HUB_1")["detectors"]["D1"]["train_id"] == "cargo_train"

    writer1.close()
    await writer1.wait_closed()
    writer2.close()
    await writer2.wait_closed()


async def test_move_command_and_ack(bus: EventBus, hub) -> None:
    mod, port = hub
    events = _collect_events(bus)
    reader, writer = await _connect_hub(port)

    command = SetSwitchPosition(
        hub_name="A_HUB_1",
        switch_name="S1",
        target=100,
    )
    await bus.publish(command)
    cmd = await _read_line(reader)
    assert cmd["cmd"] == "move"
    assert cmd["switch"] == "S1"
    assert cmd["angle"] == 100
    assert cmd["request_id"]

    await _send_line(writer, {
        "event": "move_ack",
        "hub": "A_HUB_1",
        "switch": "S1",
        "angle": 100,
        "ok": True,
        "request_id": cmd["request_id"],
    })
    await asyncio.sleep(0.05)

    acks = [e for e in events if isinstance(e, SwitchPositionChanged)]
    assert len(acks) == 1
    assert acks[0].ok is True
    assert acks[0].request_id == cmd["request_id"]

    writer.close()
    await writer.wait_closed()


async def test_move_disconnected_hub(bus: EventBus, hub) -> None:
    mod, port = hub
    events = _collect_events(bus)

    command = SetSwitchPosition(
        hub_name="A_HUB_1",
        switch_name="S1",
        target=100,
    )
    await bus.publish(command)
    await asyncio.sleep(0.05)

    acks = [e for e in events if isinstance(e, SwitchPositionChanged)]
    assert len(acks) == 1
    assert acks[0].ok is False
    assert acks[0].request_id == command.request_id


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

    await _send_line(writer, {
        "event": "tag_detected",
        "hub": "A_HUB_1",
        "detector": "D1",
        "tag_id": "04:A1:B2:C3",
    })
    await asyncio.sleep(0.05)

    info = mod.get_hub_info("A_HUB_1")
    assert info is not None
    assert info["detectors"]["D1"]["triggered"] is True
    assert info["detectors"]["D1"]["train_id"] == "arctic_express"

    writer.close()
    await writer.wait_closed()


async def test_clean_shutdown(bus: EventBus) -> None:
    mod = ArduinoHubModule(
        bus, host="127.0.0.1", port=0, hub_config=HUB_CONFIG
    )
    await mod.start()
    port = mod._server.sockets[0].getsockname()[1]

    reader, writer = await _connect_hub(port)
    await asyncio.sleep(0.05)
    assert len(mod._clients) == 1

    await mod.stop()
    await asyncio.sleep(0.05)
    assert len(mod._clients) == 0
    assert mod._server is None
    assert await asyncio.wait_for(reader.read(), timeout=2.0) == b""

    writer.close()
    await writer.wait_closed()
