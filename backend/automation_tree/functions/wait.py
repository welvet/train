from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from automation_tree.functions.base import (
    ChildrenPolicy,
    FunctionContext,
    NodeDecision,
    NodeFunction,
    require_node_config,
)
from automation_tree.model import Node
from automation_tree.validation import require_finite_number


@dataclass(frozen=True, slots=True)
class WaitConfig:
    seconds: float


class WaitFunction(NodeFunction):
    type = "wait"
    children_policy = ChildrenPolicy.REQUIRED
    fields = frozenset({"seconds"})

    def parse(self, value: Mapping[str, object], path: str) -> WaitConfig:
        return WaitConfig(
            seconds=require_finite_number(
                value["seconds"],
                f"{path}.seconds",
                minimum=0,
                maximum=3600,
            )
        )

    async def execute(
        self,
        context: FunctionContext,
        node: Node,
    ) -> NodeDecision:
        config = require_node_config(node, WaitConfig)
        await context.sleep(config.seconds)
        return NodeDecision.ENTER_CHILDREN
