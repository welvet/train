import logging

from train.core.event_bus import EventBus
from train.domain import (
    Event,
    HubConnected,
    SetSwitchPosition,
    SwitchPositionChanged,
    TagDetected,
    TrainTagRegistry,
)
from train.modules.arduino_hub.controller import ArduinoHubController
from train.modules.arduino_hub.protocol import (
    ConfigRejected,
    DetectedTag,
    Hello,
    TagChanged,
)


class FakeHubClient:
    def __init__(self) -> None:
        self.hub_name: str | None = None
        self.phase = "new"
        self.device_id: str | None = None
        self.configuration_hub: str | None = None
        self.configuration_revision: str | None = None
        self.configuration_payload: dict[str, object] | None = None
        self.closed = False
        self.moves: list[tuple[str, int, str]] = []

    def bind(self, hub_name: str) -> None:
        self.hub_name = hub_name
        self.phase = "registered"

    async def configure(
        self,
        device_id: str,
        hub_name: str,
        config: dict[str, object],
    ) -> str:
        self.device_id = device_id
        self.configuration_hub = hub_name
        self.configuration_revision = "0" * 64
        self.phase = "config_sent"
        return self.configuration_revision

    async def move_switch(
        self,
        switch_name: str,
        angle: int,
        request_id: str,
    ) -> None:
        self.moves.append((switch_name, angle, request_id))

    def close(self) -> None:
        self.closed = True


async def test_superseded_client_cannot_publish_hub_events() -> None:
    bus = EventBus()
    events: list[Event] = []

    async def collect(event: Event) -> None:
        events.append(event)

    bus.subscribe(Event, collect)
    controller = ArduinoHubController(
        bus,
        train_tags=TrainTagRegistry({"04:AA": "arctic_express"}),
        hub_config={"HUB_A": {"switches": {"S1": {}}, "detectors": ("D1",)}},
    )
    hello = Hello("HUB_A", ("S1",), ("D1",), ())
    old_client = FakeHubClient()
    current_client = FakeHubClient()

    assert await controller.handle_message(old_client, hello)
    assert await controller.handle_message(current_client, hello)
    events.clear()

    keep_open = await controller.handle_message(
        old_client,
        TagChanged("D1", "04:AA", True),
    )

    assert not keep_open
    assert old_client.closed
    assert not [event for event in events if isinstance(event, TagDetected)]
    assert controller.get_hub_info("HUB_A")["detectors"]["D1"]["triggered"] is False
    assert len([event for event in events if isinstance(event, HubConnected)]) == 0


async def test_superseded_client_cannot_reclaim_hub_identity() -> None:
    bus = EventBus()
    events: list[Event] = []

    async def collect(event: Event) -> None:
        events.append(event)

    bus.subscribe(Event, collect)
    controller = ArduinoHubController(
        bus,
        train_tags=TrainTagRegistry({"04:AA": "arctic_express"}),
        hub_config={"HUB_A": {"switches": {"S1": {}}, "detectors": ("D1",)}},
    )
    hello = Hello("HUB_A", ("S1",), ("D1",), ())
    old_client = FakeHubClient()
    current_client = FakeHubClient()

    assert await controller.handle_message(old_client, hello)
    assert await controller.handle_message(current_client, hello)
    events.clear()

    keep_open = await controller.handle_message(
        old_client,
        Hello(
            "HUB_A",
            ("S1",),
            ("D1",),
            (DetectedTag("D1", "04:AA"),),
        ),
    )

    assert not keep_open
    assert controller.clients["HUB_A"] is current_client
    assert not current_client.closed
    assert events == []
    assert controller.get_hub_info("HUB_A")["detectors"]["D1"]["triggered"] is False


async def test_integer_target_cannot_bypass_configured_switch_validation() -> None:
    bus = EventBus()
    events: list[Event] = []

    async def collect(event: Event) -> None:
        events.append(event)

    bus.subscribe(Event, collect)
    controller = ArduinoHubController(
        bus,
        train_tags=TrainTagRegistry(),
        hub_config={"HUB_A": {"switches": {"S1": {}}, "detectors": ()}},
    )
    client = FakeHubClient()
    await controller.handle_message(client, Hello("HUB_A", ("S1",), (), ()))
    events.clear()
    command = SetSwitchPosition(
        hub_name="HUB_A", switch_name="missing", target=90
    )

    await controller.set_switch(command)

    assert client.moves == []
    responses = [
        event for event in events if isinstance(event, SwitchPositionChanged)
    ]
    assert len(responses) == 1
    assert responses[0].ok is False
    assert responses[0].request_id == command.request_id


async def test_out_of_range_integer_switch_target_is_rejected() -> None:
    bus = EventBus()
    events: list[Event] = []

    async def collect(event: Event) -> None:
        events.append(event)

    bus.subscribe(Event, collect)
    controller = ArduinoHubController(
        bus,
        train_tags=TrainTagRegistry(),
        hub_config={"HUB_A": {"switches": {"S1": {}}, "detectors": ()}},
    )
    client = FakeHubClient()
    await controller.handle_message(client, Hello("HUB_A", ("S1",), (), ()))
    events.clear()

    await controller.set_switch(SetSwitchPosition(
        hub_name="HUB_A", switch_name="S1", target=181
    ))

    assert client.moves == []
    responses = [
        event for event in events if isinstance(event, SwitchPositionChanged)
    ]
    assert len(responses) == 1
    assert responses[0].ok is False


async def test_registered_runtime_client_cannot_change_applied_configuration() -> None:
    bus = EventBus()
    payload = {
        "schema": 1,
        "hub": "HUB_A",
        "servo_settle_ms": 500,
        "switches": [{"id": "S1", "pin": 9, "straight": 58, "diverge": 100}],
        "readers": [],
    }
    controller = ArduinoHubController(
        bus,
        train_tags=TrainTagRegistry(),
        hub_config={"HUB_A": {"switches": {"S1": {}}, "detectors": ()}},
    )
    client = FakeHubClient()
    client.phase = "config_sent"
    client.configuration_hub = "HUB_A"
    client.configuration_revision = "0" * 64
    client.configuration_payload = payload
    hello = Hello("HUB_A", ("S1",), (), (), "0" * 64, payload)

    assert await controller.handle_message(client, hello)

    changed = {**payload, "servo_settle_ms": 750}
    assert not await controller.handle_message(
        client,
        Hello("HUB_A", ("S1",), (), (), "0" * 64, changed),
    )


async def test_configuration_rejection_must_match_pending_device(caplog) -> None:
    controller = ArduinoHubController(
        EventBus(),
        train_tags=TrainTagRegistry(),
        hub_config={"HUB_A": {"switches": {}, "detectors": ()}},
    )
    client = FakeHubClient()

    with caplog.at_level(logging.WARNING, logger="train.hub.controller"):
        assert not await controller.handle_message(
            client,
            ConfigRejected("other-device", 1, "invalid_configuration"),
        )

    assert "unexpected configuration rejection" in caplog.text
    assert "rejected configuration:" not in caplog.text
