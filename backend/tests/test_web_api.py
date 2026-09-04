from __future__ import annotations

import asyncio

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from train.core.event_bus import EventBus
from train.core.events.hub import (
    HubConnected,
    SetSwitchPosition,
    SwitchPositionChanged,
    TagDetected,
    TagRemoved,
)
from train.core.events.train import (
    SetTrainSpeed,
    TrainConnected,
    TrainSpeedChanged,
    TrainStatus,
)
from train.modules.web_api import WebApiModule


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
async def client(bus: EventBus) -> TestClient:
    mod = WebApiModule(bus, host="127.0.0.1", port=0)
    assert mod._app is None
    await mod.start()
    assert mod._app is not None
    tc = TestClient(TestServer(mod._app))
    await tc.start_server()
    yield tc  # type: ignore[misc]
    await tc.close()
    await mod.stop()


async def test_set_speed_success(bus: EventBus, client: TestClient) -> None:
    async def fake_ble(event: SetTrainSpeed) -> None:
        await bus.publish(TrainSpeedChanged(
            train_name=event.train_name, speed=event.speed, success=True,
        ))

    bus.subscribe(SetTrainSpeed, fake_ble)

    resp = await client.post("/trains/arctic_express/speed", json={"speed": 50})
    assert resp.status == 200
    body = await resp.json()
    assert body["train_name"] == "arctic_express"
    assert body["speed"] == 50
    assert body["success"] is True


async def test_health_reports_release(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRAIN_RELEASE_ID", "release-id")

    response = await client.get("/health")

    assert response.status == 200
    assert await response.json() == {"status": "ok", "release": "release-id"}


async def test_health_reports_failed_readiness(bus: EventBus) -> None:
    mod = WebApiModule(bus, host="127.0.0.1", port=0, readiness_check=lambda: False)
    await mod.start()
    assert mod._app is not None
    client = TestClient(TestServer(mod._app))
    await client.start_server()
    try:
        response = await client.get("/health")
        assert response.status == 503
        assert (await response.json())["status"] == "error"
    finally:
        await client.close()
        await mod.stop()


async def test_set_speed_failure(bus: EventBus, client: TestClient) -> None:
    async def fake_ble(event: SetTrainSpeed) -> None:
        await bus.publish(TrainSpeedChanged(
            train_name=event.train_name, speed=event.speed, success=False,
        ))

    bus.subscribe(SetTrainSpeed, fake_ble)

    resp = await client.post("/trains/arctic_express/speed", json={"speed": 50})
    assert resp.status == 200
    body = await resp.json()
    assert body["success"] is False


async def test_set_speed_timeout(bus: EventBus, client: TestClient) -> None:
    resp = await client.post("/trains/arctic_express/speed", json={"speed": 50})
    assert resp.status == 504


async def test_missing_speed_field(bus: EventBus, client: TestClient) -> None:
    resp = await client.post("/trains/arctic_express/speed", json={})
    assert resp.status == 400


async def test_invalid_speed_value(bus: EventBus, client: TestClient) -> None:
    resp = await client.post("/trains/arctic_express/speed", json={"speed": "fast"})
    assert resp.status == 400


async def test_speed_out_of_range(bus: EventBus, client: TestClient) -> None:
    resp = await client.post("/trains/arctic_express/speed", json={"speed": 200})
    assert resp.status == 400


async def test_get_train_unknown(bus: EventBus, client: TestClient) -> None:
    resp = await client.get("/trains/nope")
    assert resp.status == 404


async def test_get_train_info(bus: EventBus, client: TestClient) -> None:
    await bus.publish(TrainConnected(train_name="arctic_express", ble_address="AA:BB"))
    await bus.publish(TrainSpeedChanged(train_name="arctic_express", speed=75, success=True))
    await bus.publish(TrainStatus(train_name="arctic_express", battery_pct=46, voltage=6.4))

    resp = await client.get("/trains/arctic_express")
    assert resp.status == 200
    body = await resp.json()
    assert body["train_name"] == "arctic_express"
    assert body["connected"] is True
    assert body["speed"] == 75
    assert body["battery_pct"] == 46
    assert body["voltage"] == 6.4


async def test_get_train_speed_resets_on_disconnect(bus: EventBus, client: TestClient) -> None:
    await bus.publish(TrainConnected(train_name="arctic_express", ble_address="AA:BB"))
    await bus.publish(TrainSpeedChanged(train_name="arctic_express", speed=50, success=True))

    resp = await client.get("/trains/arctic_express")
    body = await resp.json()
    assert body["speed"] == 50
    assert body["connected"] is True


# --- Hub endpoints ---


async def test_get_hub_unknown(bus: EventBus, client: TestClient) -> None:
    resp = await client.get("/hubs/nope")
    assert resp.status == 404


async def test_get_hub_info(bus: EventBus, client: TestClient) -> None:
    await bus.publish(HubConnected(hub_name="A_HUB_1", switches=("S1", "S2"), detectors=("D1", "D2")))
    await bus.publish(SwitchPositionChanged(hub_name="A_HUB_1", switch_name="S1", angle=100, ok=True))
    await bus.publish(TagDetected(
        hub_name="A_HUB_1", detector_name="D1", train_id="arctic_express"
    ))

    resp = await client.get("/hubs/A_HUB_1")
    assert resp.status == 200
    body = await resp.json()
    assert body["hub_name"] == "A_HUB_1"
    assert body["connected"] is True
    assert len(body["switches"]) == 2
    assert body["switches"][0] == {"name": "S1", "angle": 100}
    assert body["switches"][1] == {"name": "S2", "angle": 0}
    assert body["detectors"][0] == {
        "name": "D1",
        "triggered": True,
        "train_id": "arctic_express",
    }
    assert body["detectors"][1] == {
        "name": "D2",
        "triggered": False,
        "train_id": None,
    }

    await bus.publish(TagRemoved(
        hub_name="A_HUB_1", detector_name="D1", train_id="arctic_express"
    ))
    resp = await client.get("/hubs/A_HUB_1")
    body = await resp.json()
    assert body["detectors"][0] == {
        "name": "D1",
        "triggered": False,
        "train_id": None,
    }


async def test_set_switch_position_success(bus: EventBus, client: TestClient) -> None:
    async def fake_hub(event: SetSwitchPosition) -> None:
        angle = event.target if isinstance(event.target, int) else 58
        await bus.publish(SwitchPositionChanged(
            hub_name=event.hub_name, switch_name=event.switch_name,
            angle=angle, ok=True,
        ))

    bus.subscribe(SetSwitchPosition, fake_hub)

    resp = await client.post("/hubs/A_HUB_1/switches/S1/position", json={"angle": 100})
    assert resp.status == 200
    body = await resp.json()
    assert body["hub_name"] == "A_HUB_1"
    assert body["switch_name"] == "S1"
    assert body["angle"] == 100
    assert body["ok"] is True

    resp = await client.post(
        "/hubs/A_HUB_1/switches/S1/position", json={"position": "straight"}
    )
    assert resp.status == 200
    assert (await resp.json())["angle"] == 58


async def test_set_switch_position_timeout(bus: EventBus, client: TestClient) -> None:
    resp = await client.post("/hubs/A_HUB_1/switches/S1/position", json={"angle": 100})
    assert resp.status == 504


async def test_set_switch_position_missing_angle(bus: EventBus, client: TestClient) -> None:
    resp = await client.post("/hubs/A_HUB_1/switches/S1/position", json={})
    assert resp.status == 400
