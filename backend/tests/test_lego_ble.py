from __future__ import annotations

import asyncio
from collections.abc import Callable
from unittest.mock import patch

import pytest

from train.core.event_bus import EventBus
from train.domain import (
    Event,
    SetTrainSpeed,
    TrainConnected,
    TrainDisconnected,
    TrainSpeedChanged,
    TrainStatus,
)
from train.modules.lego_ble import HUB_CHARACTERISTIC_UUID, LegoBleModule


class FakeBleakClient:
    def __init__(self, address: str, **kwargs: object) -> None:
        self.address = address
        self.is_connected = False
        self.writes: list[tuple[str, bytes]] = []
        self._should_fail_connect = False
        self._should_fail_write = False
        self._notify_callback: Callable[..., None] | None = None

    async def connect(self) -> None:
        if self._should_fail_connect:
            raise Exception("Connection failed")
        self.is_connected = True

    async def disconnect(self) -> None:
        self.is_connected = False

    async def write_gatt_char(self, uuid: str, data: bytes, response: bool = False) -> None:
        if self._should_fail_write:
            raise Exception("Write failed")
        self.writes.append((uuid, data))

    async def start_notify(self, uuid: str, callback: Callable[..., None]) -> None:
        self._notify_callback = callback

    async def stop_notify(self, uuid: str) -> None:
        self._notify_callback = None

    def inject_notification(self, data: bytearray) -> None:
        if self._notify_callback:
            self._notify_callback(None, data)


PATCH_TARGET = "train.modules.lego_ble.BleakClient"


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


def _collect_events(bus: EventBus) -> list[Event]:
    received: list[Event] = []

    async def handler(e: Event) -> None:
        received.append(e)

    bus.subscribe(Event, handler)
    return received


async def test_scan_coalesces_callers(
    bus: EventBus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def scan() -> list[dict[str, object]]:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return [{"address": "AA:BB", "name": "Express"}]

    monkeypatch.setattr("train.modules.lego_ble.scan_lego_hubs", scan)
    mod = LegoBleModule(bus, train_map={})

    first = asyncio.create_task(mod.scan())
    await started.wait()
    second = asyncio.create_task(mod.scan())
    release.set()

    assert await asyncio.gather(first, second) == [
        [{"address": "AA:BB", "name": "Express"}],
        [{"address": "AA:BB", "name": "Express"}],
    ]
    assert calls == 1
    await mod.stop()


async def test_cancelled_caller_does_not_cancel_shared_scan(
    bus: EventBus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def scan() -> list[dict[str, object]]:
        started.set()
        await release.wait()
        return [{"address": "AA:BB", "name": "Express"}]

    monkeypatch.setattr("train.modules.lego_ble.scan_lego_hubs", scan)
    mod = LegoBleModule(bus, train_map={})
    cancelled_caller = asyncio.create_task(mod.scan())
    await started.wait()

    cancelled_caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_caller

    remaining_caller = asyncio.create_task(mod.scan())
    release.set()
    assert await remaining_caller == [{"address": "AA:BB", "name": "Express"}]
    assert mod._scan_task is None
    await mod.stop()


async def test_scan_allows_connected_hub(
    bus: EventBus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def discover() -> list[dict[str, object]]:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr("train.modules.lego_ble.scan_lego_hubs", discover)
    mod = LegoBleModule(bus, train_map={})
    mod._clients["express"] = FakeBleakClient("AA:BB")  # type: ignore[assignment]

    assert await mod.scan() == []
    assert called
    await mod.stop()


@patch(PATCH_TARGET, FakeBleakClient)
async def test_connection_waits_for_active_scan(
    bus: EventBus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def scan() -> list[dict[str, object]]:
        started.set()
        await release.wait()
        return []

    monkeypatch.setattr("train.modules.lego_ble.scan_lego_hubs", scan)
    mod = LegoBleModule(bus, train_map={"AA:BB": "express"})
    scan_task = asyncio.create_task(mod.scan())
    await started.wait()

    await mod.start()
    await asyncio.sleep(0.01)
    assert mod._clients == {}

    release.set()
    await scan_task
    await asyncio.sleep(0.05)
    assert "express" in mod._clients
    await mod.stop()


async def test_connection_attempts_remain_parallel(bus: EventBus) -> None:
    both_connecting = asyncio.Event()
    release = asyncio.Event()
    active = 0

    class BlockingBleakClient(FakeBleakClient):
        async def connect(self) -> None:
            nonlocal active
            active += 1
            if active == 2:
                both_connecting.set()
            await release.wait()
            self.is_connected = True

    with patch(PATCH_TARGET, BlockingBleakClient):
        mod = LegoBleModule(
            bus,
            train_map={"AA:BB": "express", "CC:DD": "cargo"},
        )
        await mod.start()
        await asyncio.wait_for(both_connecting.wait(), timeout=1)
        release.set()
        await asyncio.sleep(0.05)

        assert set(mod._clients) == {"express", "cargo"}
        await mod.stop()


async def test_stop_cancels_active_scan(
    bus: EventBus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()

    async def scan() -> list[dict[str, object]]:
        started.set()
        await asyncio.Event().wait()
        return []

    monkeypatch.setattr("train.modules.lego_ble.scan_lego_hubs", scan)
    mod = LegoBleModule(bus, train_map={})
    scan_task = asyncio.create_task(mod.scan())
    await started.wait()

    await mod.stop()

    with pytest.raises(asyncio.CancelledError):
        await scan_task


@patch(PATCH_TARGET, FakeBleakClient)
async def test_connect_publishes_event(bus: EventBus) -> None:
    events = _collect_events(bus)
    mod = LegoBleModule(bus, train_map={"AA:BB": "thomas"})
    await mod.start()
    await asyncio.sleep(0.1)

    connected = [e for e in events if isinstance(e, TrainConnected)]
    assert len(connected) == 1
    assert connected[0].train_name == "thomas"
    assert connected[0].ble_address == "AA:BB"

    await mod.stop()


@patch(PATCH_TARGET, FakeBleakClient)
async def test_speed_command_success(bus: EventBus) -> None:
    events = _collect_events(bus)
    mod = LegoBleModule(bus, train_map={"AA:BB": "thomas"})
    await mod.start()
    await asyncio.sleep(0.1)

    command = SetTrainSpeed(train_name="thomas", speed=75)
    await bus.publish(command)

    changed = [e for e in events if isinstance(e, TrainSpeedChanged)]
    assert len(changed) == 1
    assert changed[0].train_name == "thomas"
    assert changed[0].speed == 75
    assert changed[0].success is True
    assert changed[0].request_id == command.request_id

    await mod.stop()


@patch(PATCH_TARGET, FakeBleakClient)
async def test_speed_command_writes_correct_characteristic(bus: EventBus) -> None:
    mod = LegoBleModule(bus, train_map={"AA:BB": "thomas"})
    await mod.start()
    await asyncio.sleep(0.1)

    client = mod._clients["thomas"]
    assert isinstance(client, FakeBleakClient)
    writes_before = len(client.writes)

    await bus.publish(SetTrainSpeed(train_name="thomas", speed=50))

    new_writes = client.writes[writes_before:]
    assert len(new_writes) == 1
    assert new_writes[0][0] == HUB_CHARACTERISTIC_UUID

    await mod.stop()


@patch(PATCH_TARGET, FakeBleakClient)
async def test_speed_command_disconnected_train(bus: EventBus) -> None:
    events = _collect_events(bus)
    mod = LegoBleModule(bus, train_map={})
    await mod.start()

    command = SetTrainSpeed(train_name="unknown", speed=50)
    await bus.publish(command)

    changed = [e for e in events if isinstance(e, TrainSpeedChanged)]
    assert len(changed) == 1
    assert changed[0].success is False
    assert changed[0].request_id == command.request_id

    await mod.stop()


@patch(PATCH_TARGET)
async def test_write_failure(mock_client_cls: type, bus: EventBus) -> None:
    events = _collect_events(bus)
    fake = FakeBleakClient("AA:BB")
    mock_client_cls.return_value = fake  # type: ignore[attr-defined]

    mod = LegoBleModule(bus, train_map={"AA:BB": "thomas"})
    await mod.start()
    await asyncio.sleep(0.1)

    fake._should_fail_write = True
    command = SetTrainSpeed(train_name="thomas", speed=50)
    await bus.publish(command)

    changed = [e for e in events if isinstance(e, TrainSpeedChanged)]
    assert len(changed) == 1
    assert changed[0].success is False
    assert changed[0].request_id == command.request_id

    await mod.stop()


@patch(PATCH_TARGET)
async def test_disconnect_and_reconnect(mock_client_cls: type, bus: EventBus) -> None:
    events = _collect_events(bus)
    fake = FakeBleakClient("AA:BB")
    mock_client_cls.return_value = fake  # type: ignore[attr-defined]

    mod = LegoBleModule(bus, train_map={"AA:BB": "thomas"})
    await mod.start()
    await asyncio.sleep(0.1)

    assert any(isinstance(e, TrainConnected) for e in events)

    fake.is_connected = False
    await asyncio.sleep(1.5)

    assert any(isinstance(e, TrainDisconnected) for e in events)

    await mod.stop()


@patch(PATCH_TARGET, FakeBleakClient)
async def test_clean_shutdown(bus: EventBus) -> None:
    mod = LegoBleModule(bus, train_map={"AA:BB": "thomas"})
    await mod.start()
    await asyncio.sleep(0.1)

    assert "thomas" in mod._clients
    await mod.stop()
    assert len(mod._clients) == 0
    assert len(mod._tasks) == 0


@patch(PATCH_TARGET, FakeBleakClient)
async def test_multiple_trains(bus: EventBus) -> None:
    events = _collect_events(bus)
    mod = LegoBleModule(bus, train_map={"AA:BB": "thomas", "CC:DD": "percy"})
    await mod.start()
    await asyncio.sleep(0.1)

    connected = [e for e in events if isinstance(e, TrainConnected)]
    names = {e.train_name for e in connected}
    assert names == {"thomas", "percy"}

    await mod.stop()


@patch(PATCH_TARGET)
async def test_connect_failure_retries(mock_client_cls: type, bus: EventBus) -> None:
    events = _collect_events(bus)
    fake = FakeBleakClient("AA:BB")
    fake._should_fail_connect = True
    mock_client_cls.return_value = fake  # type: ignore[attr-defined]

    mod = LegoBleModule(bus, train_map={"AA:BB": "thomas"})
    await mod.start()
    await asyncio.sleep(0.2)

    assert not any(isinstance(e, TrainConnected) for e in events)

    await mod.stop()


async def test_empty_train_map(bus: EventBus) -> None:
    mod = LegoBleModule(bus, train_map={})
    await mod.start()
    assert len(mod._tasks) == 0
    await mod.stop()


@patch(PATCH_TARGET)
async def test_status_event_published(mock_client_cls: type, bus: EventBus) -> None:
    events = _collect_events(bus)
    fake = FakeBleakClient("AA:BB")
    mock_client_cls.return_value = fake  # type: ignore[attr-defined]

    mod = LegoBleModule(bus, train_map={"AA:BB": "thomas"})
    await mod.start()
    await asyncio.sleep(0.1)

    # Simulate hub sending battery and voltage notifications
    fake.inject_notification(bytearray([0x06, 0x00, 0x01, 0x06, 0x06, 72]))
    fake.inject_notification(bytearray([0x06, 0x00, 0x45, 0x3C, 0x30, 0x0A]))

    assert mod._battery.get("thomas") == 72
    assert mod._voltage.get("thomas") is not None

    # Trigger status publish manually
    await mod._publish_status("thomas")

    status = [e for e in events if isinstance(e, TrainStatus)]
    assert len(status) == 1
    assert status[0].train_name == "thomas"
    assert status[0].battery_pct == 72

    await mod.stop()
