from __future__ import annotations

import copy
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from train.domain.events.base import Event
from train.domain.reducers import REDUCERS


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
    unknown_tag_id: str | None = None


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
        for event_type in type(event).__mro__:
            reducer = REDUCERS.get(event_type)
            if reducer is not None:
                return reducer(self, event)
        return False

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

    def _ensure_switch(
        self, hub_id: str, switch_id: str
    ) -> tuple[SwitchState, bool]:
        hub = self._ensure_hub(hub_id)
        switch = hub.switches.get(switch_id)
        if switch is not None:
            return switch, False
        switch = SwitchState(switch_id=switch_id)
        hub.switches[switch_id] = switch
        return switch, True

    def _ensure_detector(
        self, hub_id: str, detector_id: str
    ) -> tuple[DetectorState, bool]:
        hub = self._ensure_hub(hub_id)
        detector = hub.detectors.get(detector_id)
        if detector is not None:
            return detector, False
        detector = DetectorState(detector_id=detector_id)
        hub.detectors[detector_id] = detector
        return detector, True


def _names(value: object) -> tuple[str, ...]:
    if isinstance(value, Mapping):
        return tuple(name for name in value if isinstance(name, str))
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        return ()
    return tuple(name for name in value if isinstance(name, str))


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None
