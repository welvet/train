from __future__ import annotations

from dataclasses import dataclass

from train.core.events.base import Event


@dataclass(frozen=True, slots=True)
class SetSwitchPosition(Event):
    hub_name: str = ""
    switch_name: str = ""
    target: str | int = 0


@dataclass(frozen=True, slots=True)
class SwitchPositionChanged(Event):
    hub_name: str = ""
    switch_name: str = ""
    angle: int = 0
    ok: bool = False


@dataclass(frozen=True, slots=True)
class HubConnected(Event):
    hub_name: str = ""
    switches: tuple[str, ...] = ()
    detectors: tuple[str, ...] = ()
    active_trains: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class HubDisconnected(Event):
    hub_name: str = ""


@dataclass(frozen=True, slots=True)
class TagDetected(Event):
    hub_name: str = ""
    detector_name: str = ""
    train_id: str = ""


@dataclass(frozen=True, slots=True)
class TagRemoved(Event):
    hub_name: str = ""
    detector_name: str = ""
    train_id: str = ""
