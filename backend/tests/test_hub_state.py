from train.domain.hubs import HubState, TrainPresenceChange


def test_hub_state_tracks_switches_and_train_presence() -> None:
    state = HubState.from_topology("HUB_A", ("S1",), ("D1",))

    assert state.set_switch_angle("S1", 100)
    assert state.detect_train("D1", "arctic_express") == (
        TrainPresenceChange("D1", "arctic_express", True),
    )
    assert state.active_trains == {"D1": "arctic_express"}

    assert state.remove_train("D1", "arctic_express") == (
        TrainPresenceChange("D1", "arctic_express", False),
    )
    assert state.active_trains == {}


def test_hub_state_reconciles_train_replacement_idempotently() -> None:
    state = HubState.from_topology(
        "HUB_A",
        (),
        ("D1",),
        {"D1": "arctic_express"},
    )

    assert state.detect_train("D1", "arctic_express") == ()
    assert state.remove_train("D1", "cargo_train") == ()
    assert state.detect_train("D1", "cargo_train") == (
        TrainPresenceChange("D1", "arctic_express", False),
        TrainPresenceChange("D1", "cargo_train", True),
    )

