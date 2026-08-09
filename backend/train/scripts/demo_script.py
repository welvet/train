from __future__ import annotations

import asyncio

from train.core.events.hub import DetectorChanged, HubConnected
from train.core.events.train import TrainConnected
from train.modules.automation import AutomationContext

TRAIN = "arctic_express"
HUB = "A_HUB_1"


async def demo_script(ctx: AutomationContext) -> None:
    s1_diverged = False

    async def on_train_connected(event: TrainConnected) -> None:
        await ctx.sleep(2)
        await ctx.set_speed(event.train_name, 80)

    ctx.on(TrainConnected, on_train_connected)

    await ctx.wait_for(HubConnected, filter=lambda e: e.hub_name == HUB)
    await ctx.set_switch(HUB, "S1", "straight")
    await ctx.set_switch(HUB, "S2", "straight")

    restart_task = None

    async def on_detector(event: DetectorChanged) -> None:
        nonlocal s1_diverged, restart_task

        if restart_task and not restart_task.done():
            restart_task.cancel()

        await ctx.set_speed(TRAIN, 0)

        if event.detector_name == "D1":
            s1_diverged = not s1_diverged
            await asyncio.gather(
                ctx.set_switch(HUB, "S1", "diverge" if s1_diverged else "straight"),
                ctx.set_switch(HUB, "S2", "diverge"),
            )
        elif event.detector_name == "D2":
            await ctx.set_switch(HUB, "S2", "straight")

        async def wait_and_restart() -> None:
            await ctx.sleep(5)
            await ctx.set_speed(TRAIN, 80)

        restart_task = ctx.spawn(wait_and_restart())

    ctx.on(DetectorChanged, on_detector, filter=lambda e: e.triggered, throttle=1.0)

    await ctx.wait_for(HubConnected, filter=lambda _: False)
