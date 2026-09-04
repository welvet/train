"""Stable public API for local automation programs."""

from train.core.events.hub import (
    HubConnected,
    HubDisconnected,
    SwitchPositionChanged,
    TagDetected,
    TagRemoved,
)
from train.core.events.system import AutomationHalt, AutomationResume
from train.core.events.train import (
    TrainConnected,
    TrainDisconnected,
    TrainSpeedChanged,
    TrainStatus,
)
from train.modules.automation import AutomationContext

__all__ = [
    "AutomationContext",
    "AutomationHalt",
    "AutomationResume",
    "HubConnected",
    "HubDisconnected",
    "SwitchPositionChanged",
    "TagDetected",
    "TagRemoved",
    "TrainConnected",
    "TrainDisconnected",
    "TrainSpeedChanged",
    "TrainStatus",
]
