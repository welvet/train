from __future__ import annotations

from dataclasses import dataclass

from train.domain.events.base import Event


@dataclass(frozen=True, slots=True)
class SetTrainSpeed(Event):
    train_name: str = ""
    speed: int = 0


@dataclass(frozen=True, slots=True)
class TrainSpeedChanged(Event):
    train_name: str = ""
    speed: int = 0
    success: bool = False


@dataclass(frozen=True, slots=True)
class TrainConnected(Event):
    train_name: str = ""
    ble_address: str = ""


@dataclass(frozen=True, slots=True)
class TrainDisconnected(Event):
    train_name: str = ""
    ble_address: str = ""


@dataclass(frozen=True, slots=True)
class TrainStatus(Event):
    train_name: str = ""
    battery_pct: int = 0
    voltage: float = 0.0
