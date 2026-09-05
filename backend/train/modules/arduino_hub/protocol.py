from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypeAlias


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


InboundMessage: TypeAlias = Hello | TagChanged | MoveAcknowledged | Pong


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
        return Hello(hub_name, switches, detectors, detected_tags)

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
