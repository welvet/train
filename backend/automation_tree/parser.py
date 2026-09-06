from __future__ import annotations

import json
from collections.abc import Mapping

from automation_tree.errors import AutomationParseError
from automation_tree.functions import ChildrenPolicy, FunctionRegistry
from automation_tree.model import AutomationDocument, Node, Rule, Trigger
from automation_tree.validation import (
    require_bool,
    require_fields,
    require_int,
    require_mapping,
    require_non_empty_string,
)

MAX_RULES = 1000
MAX_NODES_PER_RULE = 1000
MAX_TREE_DEPTH = 64


class AutomationParser:
    """Strict parser for version 1 and 2 configurable automation documents."""

    def __init__(
        self,
        functions: FunctionRegistry,
        *,
        max_rules: int = MAX_RULES,
        max_nodes_per_rule: int = MAX_NODES_PER_RULE,
        max_tree_depth: int = MAX_TREE_DEPTH,
    ) -> None:
        for name, value in (
            ("max_rules", max_rules),
            ("max_nodes_per_rule", max_nodes_per_rule),
            ("max_tree_depth", max_tree_depth),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        self._functions = functions
        self._max_rules = max_rules
        self._max_nodes_per_rule = max_nodes_per_rule
        self._max_tree_depth = max_tree_depth

    def parse_json(self, text: str) -> AutomationDocument:
        try:
            value = json.loads(
                text,
                object_pairs_hook=_object_without_duplicate_fields,
                parse_constant=_reject_json_constant,
            )
        except _DuplicateJsonFieldError as exc:
            raise AutomationParseError(
                "$",
                f"duplicate field in JSON object: {exc.field}",
            ) from exc
        except json.JSONDecodeError as exc:
            raise AutomationParseError(
                "$",
                f"invalid JSON at line {exc.lineno}, column {exc.colno}",
            ) from exc
        except ValueError as exc:
            raise AutomationParseError("$", f"invalid JSON: {exc}") from exc
        except RecursionError as exc:
            raise AutomationParseError(
                "$",
                "JSON nesting exceeds the decoder limit",
            ) from exc
        return self.parse(value)

    def parse(self, value: object) -> AutomationDocument:
        document = require_mapping(value, "$")
        require_fields(
            document,
            required={"version", "rules"},
            allowed={"version", "rules"},
            path="$",
        )
        version = require_int(document["version"], "$.version", minimum=1)
        if version not in (1, 2):
            raise AutomationParseError("$.version", f"unsupported version: {version}")
        raw_rules = document["rules"]
        if not isinstance(raw_rules, list):
            raise AutomationParseError("$.rules", "must be an array")
        if len(raw_rules) > self._max_rules:
            raise AutomationParseError(
                "$.rules",
                f"must contain at most {self._max_rules} rules",
            )

        rules = tuple(
            self._parse_rule(raw_rule, index, document_version=version)
            for index, raw_rule in enumerate(raw_rules)
        )
        self._validate_unique_rules(rules)
        return AutomationDocument(version=version, rules=rules)

    def _parse_rule(
        self,
        value: object,
        index: int,
        *,
        document_version: int,
    ) -> Rule:
        path = f"$.rules[{index}]"
        rule = require_mapping(value, path)
        require_fields(
            rule,
            required={"id", "enabled", "root"},
            allowed={"id", "enabled", "root"},
            path=path,
        )
        rule_id = require_non_empty_string(rule["id"], f"{path}.id")
        enabled = require_bool(rule["enabled"], f"{path}.enabled")
        trigger, children = self._parse_root(
            rule["root"],
            f"{path}.root",
            document_version=document_version,
        )
        return Rule(
            id=rule_id,
            enabled=enabled,
            trigger=trigger,
            children=children,
        )

    def _parse_root(
        self,
        value: object,
        path: str,
        *,
        document_version: int,
    ) -> tuple[Trigger, tuple[Node, ...]]:
        root = require_mapping(value, path)
        require_fields(
            root,
            required={"type", "hub_id", "detector_id", "train_id", "children"},
            allowed={"type", "hub_id", "detector_id", "train_id", "children"},
            path=path,
        )
        if root["type"] != "train_detected":
            raise AutomationParseError(
                f"{path}.type",
                "must be train_detected",
            )
        trigger = Trigger(
            hub_id=require_non_empty_string(root["hub_id"], f"{path}.hub_id"),
            detector_id=require_non_empty_string(
                root["detector_id"], f"{path}.detector_id"
            ),
            train_id=require_non_empty_string(
                root["train_id"], f"{path}.train_id"
            ),
        )
        node_count = [0]
        children = self._parse_children(
            root["children"],
            path,
            (),
            node_count,
            document_version=document_version,
            parent_type="train_detected",
        )
        if not children:
            raise AutomationParseError(f"{path}.children", "must not be empty")
        return trigger, children

    def _parse_children(
        self,
        value: object,
        parent_path: str,
        parent_node_path: tuple[int, ...],
        node_count: list[int],
        *,
        document_version: int,
        parent_type: str,
    ) -> tuple[Node, ...]:
        path = f"{parent_path}.children"
        if not isinstance(value, list):
            raise AutomationParseError(path, "must be an array")
        return tuple(
            self._parse_node(
                child,
                f"{path}[{index}]",
                (*parent_node_path, index),
                node_count,
                document_version=document_version,
                parent_type=parent_type,
            )
            for index, child in enumerate(value)
        )

    def _parse_node(
        self,
        value: object,
        path: str,
        node_path: tuple[int, ...],
        node_count: list[int],
        *,
        document_version: int,
        parent_type: str,
    ) -> Node:
        if len(node_path) > self._max_tree_depth:
            raise AutomationParseError(
                path,
                f"tree depth must not exceed {self._max_tree_depth}",
            )
        node_count[0] += 1
        if node_count[0] > self._max_nodes_per_rule:
            raise AutomationParseError(
                path,
                f"rule must contain at most {self._max_nodes_per_rule} nodes",
            )
        node = require_mapping(value, path)
        raw_type = node.get("type")
        if not isinstance(raw_type, str):
            raise AutomationParseError(f"{path}.type", "must be a string")
        if raw_type == "train_detected":
            raise AutomationParseError(
                f"{path}.type",
                "train_detected is only allowed at a rule root",
            )
        function = self._functions.get(raw_type)
        if function is None:
            raise AutomationParseError(
                f"{path}.type",
                f"unsupported node type: {raw_type}",
            )
        if document_version < function.minimum_document_version:
            raise AutomationParseError(
                f"{path}.type",
                f"requires automation document version "
                f"{function.minimum_document_version} or later",
            )
        allowed_parent_types = function.allowed_parent_types
        if (
            allowed_parent_types is not None
            and parent_type not in allowed_parent_types
        ):
            allowed = ", ".join(sorted(allowed_parent_types))
            raise AutomationParseError(
                f"{path}.type",
                f"is only allowed under: {allowed}",
            )
        required = {"type", "children", *function.fields}
        require_fields(node, required=required, allowed=required, path=path)
        raw_children = node["children"]
        if not isinstance(raw_children, list):
            raise AutomationParseError(f"{path}.children", "must be an array")
        if function.children_policy is ChildrenPolicy.REQUIRED and not raw_children:
            raise AutomationParseError(f"{path}.children", "must not be empty")
        if function.children_policy is ChildrenPolicy.FORBIDDEN and raw_children:
            raise AutomationParseError(f"{path}.children", "must be empty")
        config = function.parse(node, path)
        children = self._parse_children(
            raw_children,
            path,
            node_path,
            node_count,
            document_version=document_version,
            parent_type=raw_type,
        )
        return Node(
            type=raw_type,
            config=config,
            children=children,
            path=node_path,
        )

    @staticmethod
    def _validate_unique_rules(rules: tuple[Rule, ...]) -> None:
        ids: set[str] = set()
        enabled_triggers: dict[Trigger, str] = {}
        for index, rule in enumerate(rules):
            if rule.id in ids:
                raise AutomationParseError(
                    f"$.rules[{index}].id",
                    f"duplicate rule id: {rule.id}",
                )
            ids.add(rule.id)
            if not rule.enabled:
                continue
            existing = enabled_triggers.get(rule.trigger)
            if existing is not None:
                raise AutomationParseError(
                    f"$.rules[{index}].root",
                    f"enabled trigger is already used by rule: {existing}",
                )
            enabled_triggers[rule.trigger] = rule.id


class _DuplicateJsonFieldError(ValueError):
    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(field)


def _object_without_duplicate_fields(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonFieldError(key)
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-standard numeric constant: {value}")
