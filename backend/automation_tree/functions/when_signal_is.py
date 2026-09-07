from __future__ import annotations

from collections.abc import Mapping

from automation_tree.functions.base import (
    ChildrenPolicy,
    FunctionContext,
    NodeDecision,
    NodeFunction,
    require_node_config,
)
from automation_tree.functions.signal_condition import (
    SignalCondition,
    parse_signal_condition,
)
from automation_tree.model import Node


class WhenSignalIsFunction(NodeFunction):
    type = "when_signal_is"
    children_policy = ChildrenPolicy.REQUIRED
    fields = frozenset({"signal", "operator", "value"})
    signal_fields = frozenset({"signal"})
    minimum_document_version = 4

    def parse(self, value: Mapping[str, object], path: str) -> SignalCondition:
        return parse_signal_condition(value, path)

    async def execute(
        self,
        context: FunctionContext,
        node: Node,
    ) -> NodeDecision:
        config = require_node_config(node, SignalCondition)
        await context.wait_for_signal(config.signal, config.matches)
        return NodeDecision.ENTER_CHILDREN
