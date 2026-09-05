from __future__ import annotations

from typing import TYPE_CHECKING

from train.domain.events.hub import (
    HubConnected,
    HubDisconnected,
    SwitchPositionChanged,
    TagDetected,
    TagRemoved,
    UnknownTagDetected,
    UnknownTagRemoved,
)
from train.domain.reducers.base import set_if_different

if TYPE_CHECKING:
    from train.domain.state import SystemState


def reduce_hub_connected(state: SystemState, event: HubConnected) -> bool:
    hub = state._ensure_hub(event.hub_name)
    changed = set_if_different(hub, "connected", True)
    for switch_id in event.switches:
        _, created = state._ensure_switch(event.hub_name, switch_id)
        changed = created or changed

    available_detectors = set(event.detectors)
    active_trains = dict(event.active_trains)
    active_unknown_tags = dict(event.active_unknown_tags)
    for detector_id in available_detectors:
        _, created = state._ensure_detector(event.hub_name, detector_id)
        changed = created or changed

    for detector in hub.detectors.values():
        available = detector.detector_id in available_detectors
        train_id = active_trains.get(detector.detector_id)
        unknown_tag_id = (
            None
            if train_id is not None
            else active_unknown_tags.get(detector.detector_id)
        )
        detector_changed = set_if_different(
            detector, "available", available
        )
        detector_changed = (
            set_if_different(
                detector,
                "triggered",
                train_id is not None or unknown_tag_id is not None,
            )
            or detector_changed
        )
        detector_changed = (
            set_if_different(detector, "train_id", train_id)
            or detector_changed
        )
        detector_changed = (
            set_if_different(detector, "unknown_tag_id", unknown_tag_id)
            or detector_changed
        )
        changed = detector_changed or changed
    return changed


def reduce_hub_disconnected(
    state: SystemState, event: HubDisconnected
) -> bool:
    hub = state._ensure_hub(event.hub_name)
    changed = set_if_different(hub, "connected", False)
    for detector in hub.detectors.values():
        changed = set_if_different(detector, "available", False) or changed
    return changed


def reduce_switch_position_changed(
    state: SystemState, event: SwitchPositionChanged
) -> bool:
    if not event.ok:
        return False
    switch, _ = state._ensure_switch(event.hub_name, event.switch_name)
    return set_if_different(switch, "angle", event.angle)


def reduce_tag_detected(state: SystemState, event: TagDetected) -> bool:
    detector, _ = state._ensure_detector(
        event.hub_name, event.detector_name
    )
    changed = set_if_different(detector, "triggered", True)
    changed = set_if_different(detector, "train_id", event.train_id) or changed
    return set_if_different(detector, "unknown_tag_id", None) or changed


def reduce_tag_removed(state: SystemState, event: TagRemoved) -> bool:
    detector, _ = state._ensure_detector(
        event.hub_name, event.detector_name
    )
    if not detector.triggered or detector.train_id != event.train_id:
        return False
    detector.triggered = False
    detector.train_id = None
    return True


def reduce_unknown_tag_detected(
    state: SystemState, event: UnknownTagDetected
) -> bool:
    detector, _ = state._ensure_detector(
        event.hub_name, event.detector_name
    )
    changed = set_if_different(detector, "triggered", True)
    changed = set_if_different(detector, "train_id", None) or changed
    return (
        set_if_different(detector, "unknown_tag_id", event.tag_id)
        or changed
    )


def reduce_unknown_tag_removed(
    state: SystemState, event: UnknownTagRemoved
) -> bool:
    detector, _ = state._ensure_detector(
        event.hub_name, event.detector_name
    )
    if (
        not detector.triggered
        or detector.unknown_tag_id != event.tag_id
    ):
        return False
    detector.triggered = False
    detector.unknown_tag_id = None
    return True
