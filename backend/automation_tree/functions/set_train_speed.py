from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from automation_tree.functions.base import (
    ChildrenPolicy,
    FunctionContext,
    NodeDecision,
    NodeFunction,
    require_node_config,
)
from automation_tree.model import Node
from automation_tree.validation import require_int


@dataclass(frozen=True, slots=True)
class SetTrainSpeedConfig:
    speed: int


SetTrainSpeedHandler = Callable[
    [FunctionContext, SetTrainSpeedConfig], Awaitable[None]
]


class SetTrainSpeedFunction(NodeFunction):
    type = "set_train_speed"
    children_policy = ChildrenPolicy.FORBIDDEN
    fields = frozenset({"speed"})

    def __init__(self, handler: SetTrainSpeedHandler) -> None:
        self._handler = handler

    def parse(
        self,
        value: Mapping[str, object],
        path: str,
    ) -> SetTrainSpeedConfig:
        return SetTrainSpeedConfig(
            speed=require_int(
                value["speed"],
                f"{path}.speed",
                minimum=-100,
                maximum=100,
            )
        )

    async def execute(
        self,
        context: FunctionContext,
        node: Node,
    ) -> NodeDecision:
        config = require_node_config(node, SetTrainSpeedConfig)
        await self._handler(context, config)
        return NodeDecision.SKIP_CHILDREN
