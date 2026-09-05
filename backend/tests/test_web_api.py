from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from aiohttp import ClientResponse
from aiohttp.test_utils import TestClient, TestServer

import train.modules.web_api.transport as web_transport
from train.core.event_bus import EventBus
from train.domain import (
    AutomationHalt,
    SetSwitchPosition,
    SetTrainSpeed,
    SwitchPositionChanged,
    SystemStarted,
    SystemState,
    TrainSpeedChanged,
)
from train.modules.web_api import WebApiModule
from train.modules.web_api.static_files import StaticFileResolver


@pytest.fixture
def bus() -> EventBus:
    return EventBus(SystemState.from_topology(
        train_hubs={"express": "express_hub"},
        arduino_hubs={
            "yard": {"switches": {"S1": {}}, "detectors": ()}
        },
    ))


@pytest.fixture
async def client(bus: EventBus) -> TestClient:
    module = WebApiModule(bus, host="127.0.0.1", port=0)
    await module.start()
    assert module._app is not None
    test_client = TestClient(TestServer(module._app))
    await test_client.start_server()
    yield test_client  # type: ignore[misc]
    await test_client.close()
    await module.stop()


async def test_health_reports_release(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRAIN_RELEASE_ID", "release-id")

    response = await client.get("/health")

    assert response.status == 200
    assert await response.json() == {"status": "ok", "release": "release-id"}


async def test_health_reports_failed_readiness(bus: EventBus) -> None:
    module = WebApiModule(
        bus,
        host="127.0.0.1",
        port=0,
        readiness_check=lambda: False,
    )
    await module.start()
    assert module._app is not None
    client = TestClient(TestServer(module._app))
    await client.start_server()
    try:
        response = await client.get("/health")
        assert response.status == 503
        assert (await response.json())["status"] == "error"
    finally:
        await client.close()
        await module.stop()


async def test_state_returns_complete_domain_snapshot(
    bus: EventBus, client: TestClient
) -> None:
    await bus.publish(TrainSpeedChanged(
        train_name="express", speed=45, success=True
    ))

    response = await client.get("/api/state")

    assert response.status == 200
    envelope = await response.json()
    assert envelope["version"] == 1
    assert envelope["snapshot_at"] > 0
    body = envelope["state"]
    assert body["revision"] == 1
    assert body["trains"]["express"] == {
        "train_id": "express",
        "lego_hub_id": "express_hub",
        "speed": 45,
    }
    assert body["lego_hubs"]["express_hub"] == {
        "hub_id": "express_hub",
        "train_id": "express",
        "connected": False,
        "battery_pct": 0,
        "voltage": 0.0,
    }


async def test_openapi_exposes_state_and_public_event_contract(
    client: TestClient,
) -> None:
    response = await client.get("/api/openapi.json")

    assert response.status == 200
    body = await response.json()
    assert body["openapi"] == "3.1.0"
    assert set(body["paths"]) == {
        "/api/state",
        "/api/state/stream",
        "/api/events",
    }


async def test_state_stream_sends_initial_and_changed_full_snapshots(
    bus: EventBus, client: TestClient
) -> None:
    response = await client.get("/api/state/stream")
    try:
        assert response.status == 200
        assert response.headers["Content-Type"].startswith("text/event-stream")
        initial = await _read_state_event(response)
        assert initial["state"]["revision"] == 0

        await bus.publish(SystemStarted())

        changed = await _read_state_event(response)
        assert changed["version"] == 1
        assert changed["snapshot_at"] >= initial["snapshot_at"]
        assert changed["state"]["revision"] == 1
        assert changed["state"]["running"] is True
    finally:
        response.close()


async def test_state_stream_closes_when_module_stops(bus: EventBus) -> None:
    module = WebApiModule(bus, host="127.0.0.1", port=0)
    await module.start()
    assert module._app is not None
    client = TestClient(TestServer(module._app))
    await client.start_server()
    response = await client.get("/api/state/stream")
    try:
        await _read_state_event(response)

        await asyncio.wait_for(module.stop(), timeout=0.5)

        assert await response.content.read() == b""
    finally:
        response.close()
        await client.close()
        await module.stop()


async def test_state_stream_sends_keepalive_comments(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(web_transport, "STREAM_KEEPALIVE_INTERVAL", 0.01)
    response = await client.get("/api/state/stream")
    try:
        await _read_state_event(response)
        async with asyncio.timeout(1):
            assert await response.content.readline() == b": keepalive\n"
            assert await response.content.readline() == b"\n"
    finally:
        response.close()


async def _read_state_event(response: ClientResponse) -> dict[str, object]:
    async with asyncio.timeout(1):
        assert await response.content.readline() == b"event: state\n"
        data = await response.content.readline()
        assert await response.content.readline() == b"\n"
    return json.loads(data.removeprefix(b"data: "))


async def test_event_endpoint_decodes_and_publishes_command(
    bus: EventBus, client: TestClient
) -> None:
    received: list[SetTrainSpeed] = []

    async def handle(event: SetTrainSpeed) -> None:
        received.append(event)
        await bus.publish(TrainSpeedChanged(
            train_name=event.train_name,
            speed=event.speed,
            success=True,
            request_id=event.request_id,
        ))

    bus.subscribe(SetTrainSpeed, handle)

    response = await client.post("/api/events", json={
        "type": "set_train_speed",
        "data": {"train_id": "express", "speed": 60},
    })

    assert response.status == 200
    body = await response.json()
    assert body["completed"] is True
    assert body["command"]["type"] == "set_train_speed"
    assert body["command"]["data"]["request_id"] == received[0].request_id
    assert bus.state.trains["express"].speed == 60


async def test_event_endpoint_updates_shared_automation_state(
    bus: EventBus, client: TestClient
) -> None:
    received: list[AutomationHalt] = []

    async def handle(event: AutomationHalt) -> None:
        received.append(event)

    bus.subscribe(AutomationHalt, handle)

    response = await client.post("/api/events", json={"type": "automation_halt"})

    assert response.status == 200
    assert len(received) == 1
    assert bus.state.automation.halted is True


async def test_event_endpoint_dispatches_switch_command(
    bus: EventBus, client: TestClient
) -> None:
    received: list[SetSwitchPosition] = []

    async def handle(event: SetSwitchPosition) -> None:
        received.append(event)
        await bus.publish(SwitchPositionChanged(
            hub_name=event.hub_name,
            switch_name=event.switch_name,
            angle=90,
            ok=True,
            request_id=event.request_id,
        ))

    bus.subscribe(SetSwitchPosition, handle)

    response = await client.post("/api/events", json={
        "type": "set_switch_position",
        "data": {"hub_id": "yard", "switch_id": "S1", "target": 90},
    })

    assert response.status == 200
    assert len(received) == 1
    assert received[0].request_id == (
        await response.json()
    )["command"]["data"]["request_id"]
    assert bus.state.arduino_hubs["yard"].switches["S1"].angle == 90


async def test_event_endpoint_rejects_internal_event(client: TestClient) -> None:
    response = await client.post("/api/events", json={
        "type": "train_connected",
        "data": {"train_id": "express"},
    })

    assert response.status == 400


async def test_event_endpoint_rejects_malformed_json(client: TestClient) -> None:
    response = await client.post(
        "/api/events",
        data="{",
        headers={"Content-Type": "application/json"},
    )

    assert response.status == 400
    assert await response.json() == {"error": "body must be valid JSON"}


async def test_event_endpoint_reports_command_failure(
    bus: EventBus, client: TestClient
) -> None:
    async def reject(event: SetTrainSpeed) -> None:
        await bus.publish(TrainSpeedChanged(
            train_name=event.train_name,
            speed=event.speed,
            success=False,
            request_id=event.request_id,
        ))

    bus.subscribe(SetTrainSpeed, reject)

    response = await client.post("/api/events", json={
        "type": "set_train_speed",
        "data": {"train_id": "express", "speed": 60},
    })

    assert response.status == 409
    assert (await response.json())["error"] == "SetTrainSpeed failed"


async def test_event_endpoint_reports_unknown_train(
    client: TestClient,
) -> None:
    response = await client.post("/api/events", json={
        "type": "set_train_speed",
        "data": {"train_id": "missing", "speed": 60},
    })

    assert response.status == 404
    assert await response.json() == {"error": "unknown train: missing"}


@pytest.mark.parametrize(
    ("hub_id", "switch_id", "error"),
    [
        ("missing", "S1", "unknown Arduino hub: missing"),
        ("yard", "missing", "unknown switch: yard/missing"),
    ],
)
async def test_event_endpoint_reports_unknown_switch_resource(
    client: TestClient,
    hub_id: str,
    switch_id: str,
    error: str,
) -> None:
    response = await client.post("/api/events", json={
        "type": "set_switch_position",
        "data": {"hub_id": hub_id, "switch_id": switch_id, "target": 90},
    })

    assert response.status == 404
    assert await response.json() == {"error": error}


async def test_event_endpoint_has_bounded_command_timeout(
    bus: EventBus,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancelled = False

    async def hang(event: SetTrainSpeed) -> None:
        nonlocal cancelled
        try:
            await asyncio.sleep(10)
        finally:
            cancelled = True

    bus.subscribe(SetTrainSpeed, hang)
    monkeypatch.setattr(web_transport, "COMMAND_TIMEOUT", 0.01)

    response = await client.post("/api/events", json={
        "type": "set_train_speed",
        "data": {"train_id": "express", "speed": 60},
    })

    assert response.status == 504
    assert cancelled is True


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("GET", "/trains/express", 404),
        ("POST", "/trains/express/speed", 405),
        ("GET", "/hubs/yard", 404),
        ("POST", "/hubs/yard/switches/S1/position", 405),
        ("POST", "/halt", 405),
        ("POST", "/resume", 405),
        ("POST", "/stop", 405),
        ("GET", "/logs", 404),
    ],
)
async def test_old_api_operations_are_unavailable(
    client: TestClient,
    method: str,
    path: str,
    status: int,
) -> None:
    response = await client.request(method, path)
    assert response.status == status


async def test_serves_static_frontend_and_assets(
    bus: EventBus,
    tmp_path: Path,
) -> None:
    static_root = tmp_path / "static"
    asset = static_root / "_next" / "static" / "app.js"
    asset.parent.mkdir(parents=True)
    (static_root / "index.html").write_text("<h1>Train</h1>")
    asset.write_text("console.log('train')")
    module = WebApiModule(
        bus, host="127.0.0.1", port=0, static_root=static_root
    )
    await module.start()
    assert module._app is not None
    client = TestClient(TestServer(module._app))
    await client.start_server()
    try:
        response = await client.get("/")
        assert response.status == 200
        assert await response.text() == "<h1>Train</h1>"

        response = await client.get("/_next/static/app.js")
        assert response.status == 200
        assert await response.text() == "console.log('train')"
    finally:
        await client.close()
        await module.stop()


async def test_static_frontend_supports_exported_routes_and_404_page(
    bus: EventBus,
    tmp_path: Path,
) -> None:
    static_root = tmp_path / "static"
    static_root.mkdir()
    (static_root / "control.html").write_text("control")
    (static_root / "404.html").write_text("missing")
    module = WebApiModule(
        bus, host="127.0.0.1", port=0, static_root=static_root
    )
    await module.start()
    assert module._app is not None
    client = TestClient(TestServer(module._app))
    await client.start_server()
    try:
        response = await client.get("/control")
        assert response.status == 200
        assert await response.text() == "control"

        response = await client.get("/unknown")
        assert response.status == 404
        assert await response.text() == "missing"
    finally:
        await client.close()
        await module.stop()


def test_static_frontend_rejects_unsafe_paths(tmp_path: Path) -> None:
    static_root = tmp_path / "static"
    static_root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    resolver = StaticFileResolver(static_root)

    assert resolver._resolve("../secret.txt") is None
    assert resolver._resolve("\0") is None
