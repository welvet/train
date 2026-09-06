from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, TypeAlias

MAX_COMPONENTS = 8
MAX_ID_BYTES = 16
MAX_FRAME_BYTES = 2048
CONFIG_SCHEMA = 1


@dataclass(frozen=True, slots=True)
class DetectedTag:
    detector_name: str
    tag_id: str


@dataclass(frozen=True, slots=True)
class Hello:
    hub_name: str
    switches: tuple[str, ...]
    detectors: tuple[str, ...]
    detected_tags: tuple[DetectedTag, ...]
    revision: str | None = None
    applied: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class ConfigRequest:
    device_id: str
    schema: int


@dataclass(frozen=True, slots=True)
class ConfigRejected:
    device_id: str
    schema: int
    reason: str


@dataclass(frozen=True, slots=True)
class TagChanged:
    detector_name: str
    tag_id: str
    detected: bool


@dataclass(frozen=True, slots=True)
class MoveAcknowledged:
    switch_name: str
    angle: int
    ok: bool
    request_id: str


@dataclass(frozen=True, slots=True)
class Pong:
    pass


InboundMessage: TypeAlias = (
    Hello | ConfigRequest | ConfigRejected | TagChanged | MoveAcknowledged | Pong
)


def parse_message(line: bytes) -> InboundMessage | None:
    try:
        payload = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None

    event = payload.get("event")
    if event == "hello":
        hub_name = _required_string(payload, "hub")
        switches = _string_tuple(payload.get("switches"))
        detectors = _string_tuple(payload.get("detectors"))
        detected_tags = _detected_tags(payload.get("detected_tags", []))
        if (
            hub_name is None
            or switches is None
            or detectors is None
            or detected_tags is None
            or any(tag.detector_name not in detectors for tag in detected_tags)
        ):
            return None
        revision = payload.get("revision")
        if revision is not None and (
            not isinstance(revision, str) or len(revision) != 64
        ):
            return None
        applied = payload.get("applied")
        if applied is not None and not isinstance(applied, dict):
            return None
        return Hello(hub_name, switches, detectors, detected_tags, revision, applied)

    if event == "config_request":
        device_id = _required_string(payload, "device_id")
        schema = payload.get("schema")
        if device_id is None or schema != CONFIG_SCHEMA:
            return None
        return ConfigRequest(device_id, schema)

    if event == "config_rejected":
        device_id = _required_string(payload, "device_id")
        reason = _required_string(payload, "reason")
        schema = payload.get("schema")
        if device_id is None or reason is None or schema != CONFIG_SCHEMA:
            return None
        return ConfigRejected(device_id, schema, reason)

    if event in {"tag_detected", "tag_removed"}:
        detector_name = _required_string(payload, "detector")
        tag_id = _required_string(payload, "tag_id")
        if detector_name is None or tag_id is None:
            return None
        return TagChanged(
            detector_name=detector_name,
            tag_id=tag_id,
            detected=event == "tag_detected",
        )

    if event == "move_ack":
        switch_name = _required_string(payload, "switch")
        angle = payload.get("angle", 0)
        ok = payload.get("ok", False)
        request_id = payload.get("request_id", "")
        if (
            switch_name is None
            or not isinstance(angle, int)
            or isinstance(angle, bool)
            or not isinstance(ok, bool)
            or not isinstance(request_id, str)
            or (ok and not 0 <= angle <= 180)
        ):
            return None
        return MoveAcknowledged(
            switch_name=switch_name,
            angle=angle,
            ok=ok,
            request_id=request_id,
        )

    if event == "pong":
        return Pong()
    return None


def encode_move_command(switch_name: str, angle: int, request_id: str) -> bytes:
    return (
        json.dumps({
            "cmd": "move",
            "switch": switch_name,
            "angle": angle,
            "request_id": request_id,
        })
        + "\n"
    ).encode()


def encode_ping_command() -> bytes:
    return b'{"cmd": "ping"}\n'


def encode_configuration(
    hub_name: str, config: Mapping[str, object]
) -> tuple[bytes, str]:
    switches = config.get("switches")
    readers = config.get("readers")
    if not isinstance(switches, Mapping) or not isinstance(readers, Mapping):
        raise ValueError(f"incomplete runtime configuration for {hub_name}")
    runtime = configuration_payload(hub_name, config)
    canonical = json.dumps(
        runtime, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    revision = hashlib.sha256(canonical).hexdigest()
    envelope = {"cmd": "configure", **runtime, "revision": revision}
    encoded = (
        json.dumps(envelope, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode()
    if len(encoded) > MAX_FRAME_BYTES:
        raise ValueError(
            f"runtime configuration for {hub_name} exceeds {MAX_FRAME_BYTES} bytes"
        )
    return encoded, revision


def configuration_payload(
    hub_name: str, config: Mapping[str, object]
) -> dict[str, object]:
    switches = config.get("switches")
    readers = config.get("readers")
    if not isinstance(switches, Mapping) or not isinstance(readers, Mapping):
        raise ValueError(f"incomplete runtime configuration for {hub_name}")
    return {
        "schema": CONFIG_SCHEMA,
        "hub": hub_name,
        "servo_settle_ms": config.get("servo_settle_ms"),
        "switches": [
            {
                "id": switch_id,
                "pin": details["pin"],
                "straight": details["straight"],
                "diverge": details["diverge"],
            }
            for switch_id, details in switches.items()
        ],
        "readers": [
            {
                "id": reader_id,
                "ss_pin": details["ss_pin"],
                "read_timeout_ms": details["read_timeout_ms"],
                "removal_delay_ms": details["removal_delay_ms"],
            }
            for reader_id, details in readers.items()
        ],
    }


def validate_hello_frame_size(
    hub_name: str, config: Mapping[str, object]
) -> None:
    runtime = configuration_payload(hub_name, config)
    switches = runtime["switches"]
    readers = runtime["readers"]
    if not isinstance(switches, list) or not isinstance(readers, list):
        raise ValueError(f"invalid runtime configuration for {hub_name}")
    maximum = {
        "event": "hello",
        "hub": hub_name,
        "revision": "f" * 64,
        "applied": runtime,
        "switches": [item["id"] for item in switches],
        "detectors": [item["id"] for item in readers],
        "detected_tags": [
            {"detector": item["id"], "tag_id": "AA:BB:CC:DD:EE:FF:00"}
            for item in readers
        ],
    }
    encoded = (
        json.dumps(maximum, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode()
    if len(encoded) > MAX_FRAME_BYTES:
        raise ValueError(
            f"maximum hello for {hub_name} exceeds {MAX_FRAME_BYTES} bytes"
        )


def _string_tuple(value: object) -> tuple[str, ...] | None:
    if (
        not isinstance(value, list)
        or not all(isinstance(item, str) and item for item in value)
        or len(value) != len(set(value))
    ):
        return None
    return tuple(value)


def _detected_tags(value: object) -> tuple[DetectedTag, ...] | None:
    if not isinstance(value, list):
        return None
    detected_tags: list[DetectedTag] = []
    detector_names: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            return None
        detector_name = _required_string(item, "detector")
        tag_id = _required_string(item, "tag_id")
        if (
            detector_name is None
            or tag_id is None
            or detector_name in detector_names
        ):
            return None
        detector_names.add(detector_name)
        detected_tags.append(DetectedTag(detector_name, tag_id))
    return tuple(detected_tags)


def _required_string(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value else None
