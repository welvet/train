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
from automation_tree.functions.signal_condition import (
    MAX_SIGNAL_VALUE,
    MIN_SIGNAL_VALUE,
)
from automation_tree.model import Node
from automation_tree.validation import require_int, require_non_empty_string


@dataclass(frozen=True, slots=True)
class SetSignalConfig:
    signal: str
    value: int


class SetSignalFunction(NodeFunction):
    type = "set_signal"
    children_policy = ChildrenPolicy.FORBIDDEN
    fields = frozenset({"signal", "value"})
    signal_fields = frozenset({"signal"})
    minimum_document_version = 4

    def parse(self, value: Mapping[str, object], path: str) -> SetSignalConfig:
        return SetSignalConfig(
            signal=require_non_empty_string(value["signal"], f"{path}.signal"),
            value=require_int(
                value["value"],
                f"{path}.value",
                minimum=MIN_SIGNAL_VALUE,
                maximum=MAX_SIGNAL_VALUE,
            ),
        )

    async def execute(
        self,
        context: FunctionContext,
        node: Node,
    ) -> NodeDecision:
        config = require_node_config(node, SetSignalConfig)
        context.set_signal(config.signal, config.value)
        return NodeDecision.SKIP_CHILDREN
