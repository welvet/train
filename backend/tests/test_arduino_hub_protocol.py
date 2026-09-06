import json

import pytest

from train.modules.arduino_hub.protocol import (
    ConfigRequest,
    DetectedTag,
    Hello,
    MoveAcknowledged,
    Pong,
    TagChanged,
    encode_configuration,
    encode_move_command,
    encode_ping_command,
    parse_message,
)


def test_parse_hello_into_typed_message() -> None:
    applied = {
        "schema": 1,
        "hub": "HUB_A",
        "servo_settle_ms": 500,
        "switches": [{"id": "S1", "pin": 9, "straight": 60, "diverge": 120}],
        "readers": [{
            "id": "D1",
            "ss_pin": 4,
            "read_timeout_ms": 250,
            "removal_delay_ms": 750,
        }],
    }
    message = parse_message(json.dumps({
        "event": "hello",
        "hub": "HUB_A",
        "switches": ["S1"],
        "detectors": ["D1"],
        "detected_tags": [{"detector": "D1", "tag_id": "04:AA"}],
        "revision": "0" * 64,
        "applied": applied,
    }).encode())

    assert message == Hello(
        hub_name="HUB_A",
        switches=("S1",),
        detectors=("D1",),
        detected_tags=(DetectedTag("D1", "04:AA"),),
        revision="0" * 64,
        applied=applied,
    )


@pytest.mark.parametrize(
    "omitted_field",
    ["revision", "applied"],
)
def test_parse_hello_requires_configuration_acknowledgement(
    omitted_field: str,
) -> None:
    payload = {
        "event": "hello",
        "hub": "HUB_A",
        "switches": ["S1"],
        "detectors": [],
        "detected_tags": [],
        "revision": "0" * 64,
        "applied": {
            "schema": 1,
            "hub": "HUB_A",
            "servo_settle_ms": 500,
            "switches": [
                {"id": "S1", "pin": 9, "straight": 60, "diverge": 120}
            ],
            "readers": [],
        },
    }
    payload.pop(omitted_field)

    assert parse_message(json.dumps(payload).encode()) is None


def test_parse_configuration_request() -> None:
    assert parse_message(
        b'{"event":"config_request","schema":1,"device_id":"arduino_1"}'
    ) == ConfigRequest("arduino_1", 1)


def test_encode_runtime_configuration_with_stable_revision() -> None:
    config = {
        "servo_settle_ms": 500,
        "switches": {
            "S1": {"pin": 9, "straight": 58, "diverge": 100}
        },
        "readers": {
            "D1": {
                "ss_pin": 4,
                "read_timeout_ms": 250,
                "removal_delay_ms": 750,
            }
        },
    }
    first, revision = encode_configuration("yard", config)
    second, second_revision = encode_configuration("yard", config)

    assert first == second
    assert revision == second_revision
    assert len(revision) == 64
    payload = json.loads(first)
    assert payload["cmd"] == "configure"
    assert payload["hub"] == "yard"
    assert payload["revision"] == revision
    assert payload["switches"][0]["pin"] == 9
    assert payload["readers"][0]["ss_pin"] == 4


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"event": "tag_detected", "detector": "D1", "tag_id": "04:AA"},
            TagChanged("D1", "04:AA", True),
        ),
        (
            {"event": "tag_removed", "detector": "D1", "tag_id": "04:AA"},
            TagChanged("D1", "04:AA", False),
        ),
        (
            {
                "event": "move_ack",
                "switch": "S1",
                "angle": 100,
                "ok": True,
                "request_id": "request-1",
            },
            MoveAcknowledged("S1", 100, True, "request-1"),
        ),
        (
            {"event": "move_ack", "switch": "S1", "angle": 181, "ok": False},
            MoveAcknowledged("S1", 181, False, ""),
        ),
        ({"event": "pong"}, Pong()),
    ],
)
def test_parse_supported_messages(payload: dict[str, object], expected: object) -> None:
    assert parse_message(json.dumps(payload).encode()) == expected


@pytest.mark.parametrize(
    "line",
    [
        b"not-json",
        b"[]",
        b'{"event": "unknown"}',
        b'{"event": "hello", "hub": "HUB_A", "switches": "S1", "detectors": []}',
        b'{"event": "hello", "hub": "HUB_A", "switches": ["S1", "S1"], "detectors": []}',
        (
            b'{"event": "hello", "hub": "HUB_A", "switches": ["S1"], '
            b'"detectors": ["D1"], "detected_tags": "invalid"}'
        ),
        (
            b'{"event": "hello", "hub": "HUB_A", "switches": ["S1"], '
            b'"detectors": ["D1"], "detected_tags": [{"detector": "D1"}]}'
        ),
        (
            b'{"event": "hello", "hub": "HUB_A", "switches": ["S1"], '
            b'"detectors": ["D1"], "detected_tags": ['
            b'{"detector": "D1", "tag_id": "04:AA"}, '
            b'{"detector": "D1", "tag_id": "04:BB"}]}'
        ),
        (
            b'{"event": "hello", "hub": "HUB_A", "switches": ["S1"], '
            b'"detectors": ["D1"], "detected_tags": ['
            b'{"detector": "D2", "tag_id": "04:AA"}]}'
        ),
        b'{"event": "tag_detected", "detector": "D1", "tag_id": null}',
        b'{"event": "move_ack", "switch": "S1", "angle": "100", "ok": true}',
        b'{"event": "move_ack", "switch": "S1", "angle": 181, "ok": true}',
    ],
)
def test_invalid_messages_are_ignored(line: bytes) -> None:
    assert parse_message(line) is None


def test_encode_move_command() -> None:
    encoded = encode_move_command("S1", 100, "request-1")

    assert encoded.endswith(b"\n")
    assert json.loads(encoded) == {
        "cmd": "move",
        "switch": "S1",
        "angle": 100,
        "request_id": "request-1",
    }


def test_encode_ping_command() -> None:
    encoded = encode_ping_command()

    assert encoded.endswith(b"\n")
    assert json.loads(encoded) == {"cmd": "ping"}
