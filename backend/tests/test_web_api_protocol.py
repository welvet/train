import pytest

from train.domain import HubState
from train.modules.web_api.protocol import (
    InvalidRequest,
    hub_api_response,
    parse_speed,
    parse_switch_target,
)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"speed": 50}, 50),
        ({"speed": "-25"}, -25),
    ],
)
def test_parse_speed(payload: object, expected: int) -> None:
    assert parse_speed(payload) == expected


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"speed": "fast"},
        {"speed": 101},
    ],
)
def test_parse_speed_rejects_invalid_payload(payload: object) -> None:
    with pytest.raises(InvalidRequest):
        parse_speed(payload)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"position": "S"}, "straight"),
        ({"position": "diverge"}, "diverge"),
        ({"angle": "100"}, 100),
    ],
)
def test_parse_switch_target(payload: object, expected: str | int) -> None:
    assert parse_switch_target(payload) == expected


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"position": "left"},
        {"angle": "wide"},
        {"angle": 181},
    ],
)
def test_parse_switch_target_rejects_invalid_payload(payload: object) -> None:
    with pytest.raises(InvalidRequest):
        parse_switch_target(payload)


def test_hub_api_response_preserves_topology_order() -> None:
    state = HubState.from_topology(
        "HUB_A",
        ("S2", "S1"),
        ("D2", "D1"),
        {"D1": "arctic_express"},
    )

    assert hub_api_response(state) == {
        "hub_name": "HUB_A",
        "connected": True,
        "switches": [
            {"name": "S2", "angle": 0},
            {"name": "S1", "angle": 0},
        ],
        "detectors": [
            {"name": "D2", "triggered": False, "train_id": None},
            {
                "name": "D1",
                "triggered": True,
                "train_id": "arctic_express",
            },
        ],
    }
