from __future__ import annotations

from train.core.events.hub import DetectorChanged, HubConnected
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

    await ctx.wait_for(HubConnected, filter=lambda e: e.hub_name == HUB)

    try:
        await controller.start()
        ctx.on(
            DetectorChanged,
            controller.on_detector,
            filter=lambda e: e.hub_name == HUB and e.triggered,
        )
        await ctx.wait_for(HubConnected, filter=lambda _: False)
    finally:
        await controller.stop()
