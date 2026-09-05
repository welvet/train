from __future__ import annotations

from typing import TYPE_CHECKING

from train.domain.events.train import (
    TrainConnected,
    TrainDisconnected,
    TrainSpeedChanged,
    TrainStatus,
)
from train.domain.reducers.base import set_if_different

if TYPE_CHECKING:
    from train.domain.state import SystemState


def reduce_train_connected(
    state: SystemState, event: TrainConnected
) -> bool:
    hub = state._ensure_lego_hub(event.train_name)
    return set_if_different(hub, "connected", True)


def reduce_train_disconnected(
    state: SystemState, event: TrainDisconnected
) -> bool:
    hub = state._ensure_lego_hub(event.train_name)
    return set_if_different(hub, "connected", False)


def reduce_train_speed_changed(
    state: SystemState, event: TrainSpeedChanged
) -> bool:
    if not event.success:
        return False
    train = state._ensure_train(event.train_name)
    return set_if_different(train, "speed", event.speed)


def reduce_train_status(state: SystemState, event: TrainStatus) -> bool:
    hub = state._ensure_lego_hub(event.train_name)
    battery_changed = set_if_different(
        hub, "battery_pct", event.battery_pct
    )
    voltage_changed = set_if_different(hub, "voltage", event.voltage)
    return battery_changed or voltage_changed
