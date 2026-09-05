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
from train.modules.arduino_hub.protocol import DetectedTag, Hello, TagChanged


class FakeHubClient:
    def __init__(self) -> None:
        self.hub_name: str | None = None
        self.closed = False
        self.moves: list[tuple[str, int, str]] = []

    def bind(self, hub_name: str) -> None:
        self.hub_name = hub_name

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
