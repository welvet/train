from train.domain.events.base import Event
from train.domain.events.hub import (
    HubConnected,
    HubDisconnected,
    SwitchPositionChanged,
    TagDetected,
    TagRemoved,
    UnknownTagDetected,
    UnknownTagRemoved,
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
from train.domain.reducers.base import Reducer, adapt
from train.domain.reducers.hub import (
    reduce_hub_connected,
    reduce_hub_disconnected,
    reduce_switch_position_changed,
    reduce_tag_detected,
    reduce_tag_removed,
    reduce_unknown_tag_detected,
    reduce_unknown_tag_removed,
)
from train.domain.reducers.system import (
    reduce_automation_halt,
    reduce_automation_resume,
    reduce_system_shutdown,
    reduce_system_started,
)
from train.domain.reducers.train import (
    reduce_train_connected,
    reduce_train_disconnected,
    reduce_train_speed_changed,
    reduce_train_status,
)


REDUCERS: dict[type[Event], Reducer] = {
    SystemStarted: adapt(SystemStarted, reduce_system_started),
    SystemShutdown: adapt(SystemShutdown, reduce_system_shutdown),
    AutomationHalt: adapt(AutomationHalt, reduce_automation_halt),
    AutomationResume: adapt(AutomationResume, reduce_automation_resume),
    TrainConnected: adapt(TrainConnected, reduce_train_connected),
    TrainDisconnected: adapt(TrainDisconnected, reduce_train_disconnected),
    TrainSpeedChanged: adapt(TrainSpeedChanged, reduce_train_speed_changed),
    TrainStatus: adapt(TrainStatus, reduce_train_status),
    HubConnected: adapt(HubConnected, reduce_hub_connected),
    HubDisconnected: adapt(HubDisconnected, reduce_hub_disconnected),
    SwitchPositionChanged: adapt(
        SwitchPositionChanged, reduce_switch_position_changed
    ),
    TagDetected: adapt(TagDetected, reduce_tag_detected),
    TagRemoved: adapt(TagRemoved, reduce_tag_removed),
    UnknownTagDetected: adapt(UnknownTagDetected, reduce_unknown_tag_detected),
    UnknownTagRemoved: adapt(UnknownTagRemoved, reduce_unknown_tag_removed),
}


__all__ = ["REDUCERS"]
