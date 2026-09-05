import json

import pytest

from train.modules.arduino_hub.protocol import (
    DetectedTag,
    Hello,
    MoveAcknowledged,
    Pong,
    TagChanged,
    encode_move_command,
    encode_ping_command,
    parse_message,
)


def test_parse_hello_into_typed_message() -> None:
    message = parse_message(json.dumps({
        "event": "hello",
        "hub": "HUB_A",
        "switches": ["S1"],
        "detectors": ["D1"],
        "detected_tags": [{"detector": "D1", "tag_id": "04:AA"}],
    }).encode())

    assert message == Hello(
        hub_name="HUB_A",
        switches=("S1",),
        detectors=("D1",),
        detected_tags=(DetectedTag("D1", "04:AA"),),
    )


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
