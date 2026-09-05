from train.domain import (
    Event,
    SetTrainSpeed,
    TrainConnected,
    TrainDisconnected,
    TrainSpeedChanged,
)


def test_set_train_speed_fields() -> None:
    e = SetTrainSpeed(train_name="thomas", speed=75)
    assert e.train_name == "thomas"
    assert e.speed == 75
    assert e.request_id
    assert e.timestamp > 0


def test_train_speed_changed_fields() -> None:
    e = TrainSpeedChanged(
        train_name="percy",
        speed=50,
        success=True,
        request_id="request-1",
    )
    assert e.train_name == "percy"
    assert e.speed == 50
    assert e.success is True
    assert e.request_id == "request-1"


def test_train_connected_fields() -> None:
    e = TrainConnected(train_name="thomas", ble_address="AA:BB:CC:DD:EE:FF")
    assert e.train_name == "thomas"
    assert e.ble_address == "AA:BB:CC:DD:EE:FF"


def test_train_disconnected_fields() -> None:
    e = TrainDisconnected(train_name="thomas", ble_address="AA:BB:CC:DD:EE:FF")
    assert e.train_name == "thomas"
    assert e.ble_address == "AA:BB:CC:DD:EE:FF"


def test_all_events_are_subclass_of_event() -> None:
    for cls in (SetTrainSpeed, TrainSpeedChanged, TrainConnected, TrainDisconnected):
        assert issubclass(cls, Event)
        assert isinstance(cls(), Event)


def test_events_are_frozen() -> None:
    e = SetTrainSpeed(train_name="thomas", speed=50)
    try:
        e.speed = 100  # type: ignore[misc]
        assert False, "Should have raised"
    except AttributeError:
        pass
