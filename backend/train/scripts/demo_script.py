from __future__ import annotations

from train.core.events.hub import DetectorChanged, HubConnected
from train.modules.automation import AutomationContext
from train.scripts.pit_stop import HUB, PitStopController


async def demo_script(ctx: AutomationContext) -> None:
    await ctx.wait_for(HubConnected, filter=lambda e: e.hub_name == HUB)

    controller = PitStopController(ctx)
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
