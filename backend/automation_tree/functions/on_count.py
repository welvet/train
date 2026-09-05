from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from automation_tree.errors import AutomationParseError
from automation_tree.functions.base import (
    ChildrenPolicy,
    FunctionContext,
    NodeDecision,
    NodeFunction,
    require_node_config,
)
from automation_tree.model import Node
from automation_tree.validation import require_int


class CountMode(str, Enum):
    ONCE = "once"
    REPEAT = "repeat"


@dataclass(frozen=True, slots=True)
class OnCountConfig:
    count: int
    mode: CountMode


class OnCountFunction(NodeFunction):
    type = "on_count"
    children_policy = ChildrenPolicy.REQUIRED
    fields = frozenset({"count", "mode"})

    def parse(self, value: Mapping[str, object], path: str) -> OnCountConfig:
        count = require_int(value["count"], f"{path}.count", minimum=1)
        raw_mode = value["mode"]
        try:
            mode = CountMode(raw_mode)
        except (TypeError, ValueError) as exc:
            raise AutomationParseError(
                f"{path}.mode",
                "must be once or repeat",
            ) from exc
        return OnCountConfig(count=count, mode=mode)

    async def execute(
        self,
        context: FunctionContext,
        node: Node,
    ) -> NodeDecision:
        config = require_node_config(node, OnCountConfig)
        occurrence = context.next_count(node.path)
        if config.mode is CountMode.ONCE:
            matches = occurrence == config.count
        else:
            matches = occurrence % config.count == 0
        if matches:
            return NodeDecision.ENTER_CHILDREN
        return NodeDecision.SKIP_CHILDREN
