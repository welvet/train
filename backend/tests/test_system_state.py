from train.domain import (
    AutomationHalt,
    HubConnected,
    HubDisconnected,
    SetTrainSpeed,
    SwitchPositionChanged,
    SystemState,
    TagDetected,
    TagRemoved,
    TrainConnected,
    TrainSpeedChanged,
    TrainStatus,
)


def test_state_starts_with_configured_disconnected_topology() -> None:
    state = SystemState.from_topology(
        train_hubs={"express": "hub_red"},
        arduino_hubs={
            "yard": {
                "device_id": "arduino_1",
                "switches": {"S1": {}},
                "detectors": ("D1", "D2"),
            }
        },
    )

    assert state.trains["express"].lego_hub_id == "hub_red"
    assert state.lego_hubs["hub_red"].connected is False
    hub = state.arduino_hubs["yard"]
    assert hub.device_id == "arduino_1"
    assert hub.connected is False
    assert list(hub.switches) == ["S1"]
    assert list(hub.detectors) == ["D1", "D2"]


def test_state_reduces_train_and_automation_events() -> None:
    state = SystemState.from_topology(train_hubs={"express": "hub_red"})

    state.apply(TrainConnected(train_name="express"))
    state.apply(TrainStatus(
        train_name="express", battery_pct=72, voltage=7.4
    ))
    state.apply(TrainSpeedChanged(
        train_name="express", speed=50, success=True
    ))
    state.apply(AutomationHalt())

    train = state.trains["express"]
    lego_hub = state.lego_hubs[train.lego_hub_id]
    assert train.speed == 50
    assert lego_hub.connected is True
    assert lego_hub.battery_pct == 72
    assert lego_hub.voltage == 7.4
    assert state.automation.halted is True
    assert state.revision == 4

    state.apply(SetTrainSpeed(train_name="express", speed=10))
    state.apply(TrainSpeedChanged(
        train_name="express", speed=10, success=False
    ))
    assert train.speed == 50
    assert state.revision == 4


def test_state_reconciles_hub_snapshot_and_tag_events() -> None:
    state = SystemState.from_topology(
        arduino_hubs={
            "yard": {
                "switches": {"S1": {}},
                "detectors": ("D1", "D2"),
            }
        }
    )

    state.apply(HubConnected(
        hub_name="yard",
        switches=("S1",),
        detectors=("D1",),
        active_trains=(("D1", "express"),),
    ))
    state.apply(SwitchPositionChanged(
        hub_name="yard", switch_name="S1", angle=100, ok=True
    ))

    hub = state.arduino_hubs["yard"]
    assert hub.connected is True
    assert hub.switches["S1"].angle == 100
    assert hub.detectors["D1"].available is True
    assert hub.detectors["D1"].train_id == "express"
    assert hub.detectors["D2"].available is False

    state.apply(TagRemoved(
        hub_name="yard", detector_name="D1", train_id="stale"
    ))
    assert hub.detectors["D1"].train_id == "express"

    state.apply(TagRemoved(
        hub_name="yard", detector_name="D1", train_id="express"
    ))
    state.apply(TagDetected(
        hub_name="yard", detector_name="D1", train_id="cargo"
    ))
    assert hub.detectors["D1"].train_id == "cargo"

    state.apply(HubDisconnected(hub_name="yard"))
    assert hub.connected is False
    assert hub.detectors["D1"].available is False
    assert hub.detectors["D1"].train_id == "cargo"


def test_snapshot_is_isolated_from_live_state() -> None:
    state = SystemState.from_topology(train_hubs={"express": "hub_red"})

    snapshot = state.snapshot()
    snapshot.trains["express"].speed = 90

    assert state.trains["express"].speed == 0
