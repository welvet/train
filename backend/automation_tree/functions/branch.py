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


class BranchWhen(str, Enum):
    MATCH = "match"
    OTHERWISE = "otherwise"


@dataclass(frozen=True, slots=True)
class BranchConfig:
    when: BranchWhen


class BranchFunction(NodeFunction):
    type = "branch"
    children_policy = ChildrenPolicy.REQUIRED
    fields = frozenset({"when"})
    allowed_parent_types = frozenset({"if_count"})
    minimum_document_version = 2

    def parse(self, value: Mapping[str, object], path: str) -> BranchConfig:
        try:
            when = BranchWhen(value["when"])
        except (TypeError, ValueError) as exc:
            raise AutomationParseError(
                f"{path}.when",
                "must be match or otherwise",
            ) from exc
        return BranchConfig(when=when)

    async def execute(
        self,
        context: FunctionContext,
        node: Node,
    ) -> NodeDecision:
        require_node_config(node, BranchConfig)
        return NodeDecision.ENTER_CHILDREN
