from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TrainPresenceChange:
    detector_name: str
    train_id: str
    detected: bool


@dataclass(slots=True)
class SwitchState:
    name: str
    angle: int = 0


@dataclass(slots=True)
class DetectorState:
    name: str
    triggered: bool = False
    train_id: str | None = None


@dataclass(slots=True)
class HubState:
    hub_name: str
    connected: bool
    switches: dict[str, SwitchState]
    detectors: dict[str, DetectorState]

    @classmethod
    def from_topology(
        cls,
        hub_name: str,
        switches: Iterable[str],
        detectors: Iterable[str],
        active_trains: Mapping[str, str] | None = None,
    ) -> HubState:
        active = active_trains or {}
        return cls(
            hub_name=hub_name,
            connected=True,
            switches={name: SwitchState(name) for name in switches},
            detectors={
                name: DetectorState(
                    name=name,
                    triggered=name in active,
                    train_id=active.get(name),
                )
                for name in detectors
            },
        )

    @property
    def active_trains(self) -> dict[str, str]:
        return {
            name: detector.train_id
            for name, detector in self.detectors.items()
            if detector.triggered and detector.train_id is not None
        }

    def set_switch_angle(self, switch_name: str, angle: int) -> bool:
        switch = self.switches.get(switch_name)
        if switch is None:
            return False
        switch.angle = angle
        return True

    def detect_train(
        self,
        detector_name: str,
        train_id: str,
    ) -> tuple[TrainPresenceChange, ...]:
        detector = self.detectors.get(detector_name)
        if detector is None:
            return ()
        active_train_id = detector.train_id if detector.triggered else None
        if active_train_id == train_id:
            return ()

        changes: list[TrainPresenceChange] = []
        if active_train_id is not None:
            changes.append(TrainPresenceChange(detector_name, active_train_id, False))
        detector.triggered = True
        detector.train_id = train_id
        changes.append(TrainPresenceChange(detector_name, train_id, True))
        return tuple(changes)

    def remove_train(
        self,
        detector_name: str,
        train_id: str,
    ) -> tuple[TrainPresenceChange, ...]:
        detector = self.detectors.get(detector_name)
        if (
            detector is None
            or not detector.triggered
            or detector.train_id != train_id
        ):
            return ()
        detector.triggered = False
        detector.train_id = None
        return (TrainPresenceChange(detector_name, train_id, False),)
