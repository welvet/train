from __future__ import annotations

from typing import Any

from train.domain import HubState


class InvalidRequest(ValueError):
    pass


def parse_speed(payload: object) -> int:
    if not isinstance(payload, dict):
        raise InvalidRequest('body must be {"speed": <int>}')
    try:
        speed = int(payload["speed"])
    except (KeyError, ValueError, TypeError):
        raise InvalidRequest('body must be {"speed": <int>}') from None
    if not -100 <= speed <= 100:
        raise InvalidRequest("speed must be between -100 and 100")
    return speed


def parse_switch_target(payload: object) -> str | int:
    if not isinstance(payload, dict):
        raise InvalidRequest("body must contain position or angle")
    if "position" in payload and isinstance(payload["position"], str):
        target = payload["position"].lower()
        target = {"s": "straight", "d": "diverge"}.get(target, target)
        if target not in {"straight", "diverge"}:
            raise InvalidRequest("position must be straight or diverge")
        return target
    if "angle" in payload:
        try:
            target = int(payload["angle"])
        except (ValueError, TypeError):
            raise InvalidRequest("angle must be an integer") from None
        if not 0 <= target <= 180:
            raise InvalidRequest("angle must be in 0..180")
        return target
    raise InvalidRequest("body must contain position or angle")


def hub_api_response(state: HubState) -> dict[str, Any]:
    return {
        "hub_name": state.hub_name,
        "connected": state.connected,
        "switches": [
            {"name": switch.name, "angle": switch.angle}
            for switch in state.switches.values()
        ],
        "detectors": [
            {
                "name": detector.name,
                "triggered": detector.triggered,
                "train_id": detector.train_id,
            }
            for detector in state.detectors.values()
        ],
    }
