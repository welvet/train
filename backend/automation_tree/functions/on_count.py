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
from automation_tree.validation import require_int


@dataclass(frozen=True, slots=True)
class OnCountConfig:
    count: int


class OnCountFunction(NodeFunction):
    type = "on_count"
    children_policy = ChildrenPolicy.REQUIRED
    fields = frozenset({"count"})

    def parse(self, value: Mapping[str, object], path: str) -> OnCountConfig:
        count = require_int(value["count"], f"{path}.count", minimum=1)
        return OnCountConfig(count=count)

    async def execute(
        self,
        context: FunctionContext,
        node: Node,
    ) -> NodeDecision:
        config = require_node_config(node, OnCountConfig)
        occurrence = context.next_count(node.path)
        if occurrence % config.count == 0:
            return NodeDecision.ENTER_CHILDREN
        return NodeDecision.SKIP_CHILDREN
