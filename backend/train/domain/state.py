from __future__ import annotations

import copy
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from train.domain.events.base import Event
from train.domain.events.hub import (
    HubConnected,
    HubDisconnected,
    SwitchPositionChanged,
    TagDetected,
    TagRemoved,
)
from train.domain.events.system import (
    AutomationHalt,
    AutomationResume,
    SystemShutdown,
    SystemStarted,
)
from train.domain.events.train import (
    TrainConnected,
    TrainDisconnected,
    TrainSpeedChanged,
    TrainStatus,
)


@dataclass(slots=True)
class AutomationState:
    halted: bool = False


@dataclass(slots=True)
class LegoHubState:
    hub_id: str
    train_id: str
    connected: bool = False
    battery_pct: int = 0
    voltage: float = 0.0


@dataclass(slots=True)
class TrainState:
    train_id: str
    lego_hub_id: str
    speed: int = 0


@dataclass(slots=True)
class SwitchState:
    switch_id: str
    angle: int = 0


@dataclass(slots=True)
class DetectorState:
    detector_id: str
    available: bool = False
    triggered: bool = False
    train_id: str | None = None


@dataclass(slots=True)
class ArduinoHubState:
    hub_id: str
    device_id: str | None = None
    connected: bool = False
    switches: dict[str, SwitchState] = field(default_factory=dict)
    detectors: dict[str, DetectorState] = field(default_factory=dict)


@dataclass(slots=True)
class SystemState:
    revision: int = 0
    updated_at: float = field(default_factory=time.time)
    running: bool = False
    automation: AutomationState = field(default_factory=AutomationState)
    trains: dict[str, TrainState] = field(default_factory=dict)
    lego_hubs: dict[str, LegoHubState] = field(default_factory=dict)
    arduino_hubs: dict[str, ArduinoHubState] = field(default_factory=dict)

    @classmethod
    def from_topology(
        cls,
        *,
        train_hubs: Mapping[str, str] | None = None,
        arduino_hubs: Mapping[str, Mapping[str, object]] | None = None,
    ) -> SystemState:
        state = cls()
        for train_id, lego_hub_id in (train_hubs or {}).items():
            state._ensure_train(train_id, lego_hub_id=lego_hub_id)
        for hub_id, topology in (arduino_hubs or {}).items():
            raw_switches = topology.get("switches", {})
            raw_detectors = topology.get("detectors", ())
            state.arduino_hubs[hub_id] = ArduinoHubState(
                hub_id=hub_id,
                device_id=_optional_string(topology.get("device_id")),
                switches={
                    switch_id: SwitchState(switch_id=switch_id)
                    for switch_id in _names(raw_switches)
                },
                detectors={
                    detector_id: DetectorState(detector_id=detector_id)
                    for detector_id in _names(raw_detectors)
                },
            )
        return state

    def snapshot(self) -> SystemState:
        return copy.deepcopy(self)

    def apply(self, event: Event) -> None:
        changed = self._reduce(event)
        if changed:
            self.revision += 1
            self.updated_at = event.timestamp

    def _reduce(self, event: Event) -> bool:
        if isinstance(event, SystemStarted):
            return _set_if_different(self, "running", True)
        if isinstance(event, SystemShutdown):
            return _set_if_different(self, "running", False)
        if isinstance(event, AutomationHalt):
            return _set_if_different(self.automation, "halted", True)
        if isinstance(event, AutomationResume):
            return _set_if_different(self.automation, "halted", False)
        if isinstance(event, TrainConnected):
            hub = self._ensure_lego_hub(event.train_name)
            return _set_if_different(hub, "connected", True)
        if isinstance(event, TrainDisconnected):
            hub = self._ensure_lego_hub(event.train_name)
            return _set_if_different(hub, "connected", False)
        if isinstance(event, TrainSpeedChanged):
            if not event.success:
                return False
            train = self._ensure_train(event.train_name)
            return _set_if_different(train, "speed", event.speed)
        if isinstance(event, TrainStatus):
            hub = self._ensure_lego_hub(event.train_name)
            battery_changed = _set_if_different(
                hub, "battery_pct", event.battery_pct
            )
            voltage_changed = _set_if_different(hub, "voltage", event.voltage)
            return battery_changed or voltage_changed
        if isinstance(event, HubConnected):
            return self._connect_hub(event)
        if isinstance(event, HubDisconnected):
            hub = self._ensure_hub(event.hub_name)
            changed = _set_if_different(hub, "connected", False)
            for detector in hub.detectors.values():
                changed = (
                    _set_if_different(detector, "available", False) or changed
                )
            return changed
        if isinstance(event, SwitchPositionChanged):
            if not event.ok:
                return False
            hub = self._ensure_hub(event.hub_name)
            switch = hub.switches.setdefault(
                event.switch_name,
                SwitchState(switch_id=event.switch_name),
            )
            return _set_if_different(switch, "angle", event.angle)
        if isinstance(event, TagDetected):
            detector = self._ensure_detector(
                event.hub_name, event.detector_name
            )
            changed = _set_if_different(detector, "triggered", True)
            return _set_if_different(detector, "train_id", event.train_id) or changed
        if isinstance(event, TagRemoved):
            detector = self._ensure_detector(
                event.hub_name, event.detector_name
            )
            if not detector.triggered or detector.train_id != event.train_id:
                return False
            detector.triggered = False
            detector.train_id = None
            return True
        return False

    def _connect_hub(self, event: HubConnected) -> bool:
        hub = self._ensure_hub(event.hub_name)
        changed = _set_if_different(hub, "connected", True)
        for switch_id in event.switches:
            if switch_id not in hub.switches:
                hub.switches[switch_id] = SwitchState(switch_id=switch_id)
                changed = True
        available_detectors = set(event.detectors)
        active_trains = dict(event.active_trains)
        for detector_id in available_detectors:
            if detector_id not in hub.detectors:
                hub.detectors[detector_id] = DetectorState(
                    detector_id=detector_id
                )
                changed = True
        for detector in hub.detectors.values():
            available = detector.detector_id in available_detectors
            train_id = active_trains.get(detector.detector_id)
            detector_changed = _set_if_different(
                detector, "available", available
            )
            detector_changed = (
                _set_if_different(detector, "triggered", train_id is not None)
                or detector_changed
            )
            detector_changed = (
                _set_if_different(detector, "train_id", train_id)
                or detector_changed
            )
            changed = detector_changed or changed
        return changed

    def _ensure_train(
        self, train_id: str, *, lego_hub_id: str | None = None
    ) -> TrainState:
        resolved_hub_id = lego_hub_id or train_id
        train = self.trains.setdefault(
            train_id,
            TrainState(train_id=train_id, lego_hub_id=resolved_hub_id),
        )
        self.lego_hubs.setdefault(
            train.lego_hub_id,
            LegoHubState(hub_id=train.lego_hub_id, train_id=train_id),
        )
        return train

    def _ensure_lego_hub(self, train_id: str) -> LegoHubState:
        train = self._ensure_train(train_id)
        return self.lego_hubs[train.lego_hub_id]

    def _ensure_hub(self, hub_id: str) -> ArduinoHubState:
        return self.arduino_hubs.setdefault(
            hub_id, ArduinoHubState(hub_id=hub_id)
        )

    def _ensure_detector(
        self, hub_id: str, detector_id: str
    ) -> DetectorState:
        hub = self._ensure_hub(hub_id)
        return hub.detectors.setdefault(
            detector_id, DetectorState(detector_id=detector_id)
        )


def _set_if_different(target: object, field_name: str, value: object) -> bool:
    if getattr(target, field_name) == value:
        return False
    setattr(target, field_name, value)
    return True


def _names(value: object) -> tuple[str, ...]:
    if isinstance(value, Mapping):
        return tuple(name for name in value if isinstance(name, str))
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        return ()
    return tuple(name for name in value if isinstance(name, str))


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None
