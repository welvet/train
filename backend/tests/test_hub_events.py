from train.core.events import Event
from train.core.events.hub import (
    HubConnected,
    HubDisconnected,
    SetSwitchPosition,
    SwitchPositionChanged,
    TagDetected,
    TagRemoved,
)


def test_set_switch_position_fields() -> None:
    e = SetSwitchPosition(hub_name="A_HUB_1", switch_name="S1", target=100)
    assert e.hub_name == "A_HUB_1"
    assert e.switch_name == "S1"
    assert e.target == 100
    assert e.timestamp > 0


def test_switch_position_changed_fields() -> None:
    e = SwitchPositionChanged(hub_name="A_HUB_1", switch_name="S1", angle=100, ok=True)
    assert e.hub_name == "A_HUB_1"
    assert e.switch_name == "S1"
    assert e.angle == 100
    assert e.ok is True


def test_hub_connected_fields() -> None:
    e = HubConnected(
        hub_name="A_HUB_1",
        switches=("S1", "S2"),
        detectors=("D1", "D2"),
        active_trains=(("D1", "arctic_express"),),
    )
    assert e.hub_name == "A_HUB_1"
    assert e.switches == ("S1", "S2")
    assert e.detectors == ("D1", "D2")
    assert e.active_trains == (("D1", "arctic_express"),)


def test_hub_disconnected_fields() -> None:
    e = HubDisconnected(hub_name="A_HUB_1")
    assert e.hub_name == "A_HUB_1"


def test_tag_detector_event_fields() -> None:
    detected = TagDetected(
        hub_name="A_HUB_1", detector_name="D1", train_id="arctic_express"
    )
    removed = TagRemoved(
        hub_name="A_HUB_1", detector_name="D1", train_id="arctic_express"
    )
    assert detected.hub_name == "A_HUB_1"
    assert detected.detector_name == "D1"
    assert detected.train_id == "arctic_express"
    assert removed.train_id == "arctic_express"


def test_all_events_are_subclass_of_event() -> None:
    for cls in (
        SetSwitchPosition,
        SwitchPositionChanged,
        HubConnected,
        HubDisconnected,
        TagDetected,
        TagRemoved,
    ):
        assert issubclass(cls, Event)
        assert isinstance(cls(), Event)


def test_events_are_frozen() -> None:
    e = SetSwitchPosition(hub_name="A_HUB_1", switch_name="S1", target=100)
    try:
        e.angle = 50  # type: ignore[misc]
        assert False, "Should have raised"
    except AttributeError:
        pass
