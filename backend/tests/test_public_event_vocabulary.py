import pytest

from train.domain import (
    AutomationHalt,
    InvalidPublicEvent,
    SetSwitchPosition,
    SetTrainSpeed,
    TrainConnected,
    decode_public_event,
    encode_public_event,
)


def test_decodes_public_command_events() -> None:
    speed = decode_public_event({
        "type": "set_train_speed",
        "data": {"train_id": "express", "speed": -40},
    })
    switch = decode_public_event({
        "type": "set_switch_position",
        "data": {"hub_id": "yard", "switch_id": "S1", "target": "d"},
    })

    assert isinstance(speed, SetTrainSpeed)
    assert speed.train_name == "express"
    assert speed.speed == -40
    assert isinstance(switch, SetSwitchPosition)
    assert switch.target == "diverge"


def test_encodes_event_with_stable_wire_names() -> None:
    event = SetTrainSpeed(train_name="express", speed=25, request_id="request-1")

    assert encode_public_event(event) == {
        "type": "set_train_speed",
        "data": {
            "train_id": "express",
            "speed": 25,
            "request_id": "request-1",
        },
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "train_connected", "data": {"train_id": "express"}},
        {"type": "set_train_speed", "data": {"train_id": "express", "speed": True}},
        {"type": "set_train_speed", "data": {"train_id": "express", "speed": 101}},
        {"type": "set_switch_position", "data": {"hub_id": "yard", "switch_id": "S1", "target": 181}},
    ],
)
def test_rejects_unsupported_or_invalid_events(payload: object) -> None:
    with pytest.raises(InvalidPublicEvent):
        decode_public_event(payload)


def test_internal_events_cannot_be_encoded_as_public_commands() -> None:
    with pytest.raises(InvalidPublicEvent):
        encode_public_event(TrainConnected(train_name="express"))


def test_control_event_data_defaults_to_empty_object() -> None:
    assert isinstance(decode_public_event({"type": "automation_halt"}), AutomationHalt)


def test_external_request_id_cannot_override_generated_correlation() -> None:
    event = decode_public_event({
        "type": "set_train_speed",
        "data": {
            "train_id": "express",
            "speed": 25,
            "request_id": "external-request",
        },
    })

    assert isinstance(event, SetTrainSpeed)
    assert event.request_id != "external-request"
