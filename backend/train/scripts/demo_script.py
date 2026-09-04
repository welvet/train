from __future__ import annotations

from train.core.events.hub import HubConnected, TagDetected, TagRemoved
from train.core.events.train import TrainSpeedChanged
from train.modules.automation import AutomationContext
from train.scripts.pit_stop import HUB, TRAIN, PitStopController


async def demo_script(ctx: AutomationContext) -> None:
    controller = PitStopController(ctx)
    ctx.on(
        TrainSpeedChanged,
        controller.on_speed_changed,
        filter=lambda e: e.train_name == TRAIN and e.success,
    )

    ctx.on(
        TagDetected,
        controller.on_tag_detected,
        filter=lambda e: e.hub_name == HUB and e.train_id == TRAIN,
    )
    ctx.on(
        TagRemoved,
        controller.on_tag_removed,
        filter=lambda e: e.hub_name == HUB and e.train_id == TRAIN,
    )

    await ctx.wait_for(HubConnected, filter=lambda e: e.hub_name == HUB)

    try:
        await controller.start()
        await ctx.wait_for(HubConnected, filter=lambda _: False)
    finally:
        await controller.stop()
