from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from automation_tree.errors import AutomationParseError
from automation_tree.functions.base import (
    ChildSelection,
    ChildrenPolicy,
    FunctionContext,
    NodeFunction,
    require_node_config,
)
from automation_tree.functions.branch import BranchWhen
from automation_tree.model import Node
from automation_tree.validation import require_int, require_mapping


@dataclass(frozen=True, slots=True)
class IfCountConfig:
    count: int
    match_index: int
    otherwise_index: int


class IfCountFunction(NodeFunction):
    type = "if_count"
    children_policy = ChildrenPolicy.REQUIRED
    fields = frozenset({"count"})
    minimum_document_version = 2

    def parse(self, value: Mapping[str, object], path: str) -> IfCountConfig:
        raw_children = value["children"]
        if not isinstance(raw_children, list) or len(raw_children) != 2:
            raise AutomationParseError(
                f"{path}.children",
                "must contain exactly one match branch and one otherwise branch",
            )

        branch_indices: dict[BranchWhen, int] = {}
        for index, raw_child in enumerate(raw_children):
            child_path = f"{path}.children[{index}]"
            child = require_mapping(raw_child, child_path)
            if child.get("type") != "branch":
                raise AutomationParseError(
                    f"{child_path}.type",
                    "must be branch",
                )
            raw_when = child.get("when")
            try:
                when = BranchWhen(raw_when)
            except (TypeError, ValueError) as exc:
                raise AutomationParseError(
                    f"{child_path}.when",
                    "must be match or otherwise",
                ) from exc
            if when in branch_indices:
                raise AutomationParseError(
                    f"{child_path}.when",
                    f"duplicate {when.value} branch",
                )
            branch_indices[when] = index

        missing = set(BranchWhen) - branch_indices.keys()
        if missing:
            when = sorted(item.value for item in missing)[0]
            raise AutomationParseError(
                f"{path}.children",
                f"missing {when} branch",
            )

        return IfCountConfig(
            count=require_int(value["count"], f"{path}.count", minimum=1),
            match_index=branch_indices[BranchWhen.MATCH],
            otherwise_index=branch_indices[BranchWhen.OTHERWISE],
        )

    async def execute(
        self,
        context: FunctionContext,
        node: Node,
    ) -> ChildSelection:
        config = require_node_config(node, IfCountConfig)
        occurrence = context.next_count(node.path)
        index = (
            config.match_index
            if occurrence % config.count == 0
            else config.otherwise_index
        )
        return ChildSelection(index=index)
