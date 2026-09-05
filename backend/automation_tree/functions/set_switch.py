from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
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
from automation_tree.validation import require_non_empty_string


class SwitchPosition(str, Enum):
    STRAIGHT = "straight"
    DIVERGE = "diverge"


@dataclass(frozen=True, slots=True)
class SetSwitchConfig:
    hub_id: str
    switch_id: str
    position: SwitchPosition


SetSwitchHandler = Callable[[FunctionContext, SetSwitchConfig], Awaitable[None]]


class SetSwitchFunction(NodeFunction):
    type = "set_switch"
    children_policy = ChildrenPolicy.FORBIDDEN
    fields = frozenset({"hub_id", "switch_id", "position"})

    def __init__(self, handler: SetSwitchHandler) -> None:
        self._handler = handler

    def parse(self, value: Mapping[str, object], path: str) -> SetSwitchConfig:
        raw_position = value["position"]
        try:
            position = SwitchPosition(raw_position)
        except (TypeError, ValueError) as exc:
            raise AutomationParseError(
                f"{path}.position",
                "must be straight or diverge",
            ) from exc
        return SetSwitchConfig(
            hub_id=require_non_empty_string(value["hub_id"], f"{path}.hub_id"),
            switch_id=require_non_empty_string(
                value["switch_id"], f"{path}.switch_id"
            ),
            position=position,
        )

    async def execute(
        self,
        context: FunctionContext,
        node: Node,
    ) -> NodeDecision:
        config = require_node_config(node, SetSwitchConfig)
        await self._handler(context, config)
        return NodeDecision.SKIP_CHILDREN
