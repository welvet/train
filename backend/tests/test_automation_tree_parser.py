from __future__ import annotations

from collections.abc import Mapping

import pytest

from automation_tree import (
    AutomationParseError,
    AutomationParser,
    BranchFunction,
    DuplicateFunctionError,
    FunctionRegistry,
    IfCountFunction,
    OnCountFunction,
    SetSwitchFunction,
    SetTrainSpeedFunction,
    WaitFunction,
)
from automation_tree.functions import (
    ChildrenPolicy,
    BranchConfig,
    FunctionContext,
    IfCountConfig,
    NodeDecision,
    NodeFunction,
    OnCountConfig,
    SetSwitchConfig,
    SetTrainSpeedConfig,
    WaitConfig,
)
from automation_tree.model import Node


async def _set_speed(
    context: FunctionContext,
    config: SetTrainSpeedConfig,
) -> None:
    pass


async def _set_switch(
    context: FunctionContext,
    config: SetSwitchConfig,
) -> None:
    pass


@pytest.fixture
def parser() -> AutomationParser:
    return AutomationParser(FunctionRegistry([
        WaitFunction(),
        BranchFunction(),
        IfCountFunction(),
        OnCountFunction(),
        SetTrainSpeedFunction(_set_speed),
        SetSwitchFunction(_set_switch),
    ]))


def _document(*rules: object, version: int = 1) -> dict[str, object]:
    return {"version": version, "rules": list(rules)}


def _rule(
    *children: object,
    rule_id: str = "departure",
    enabled: bool = True,
    hub_id: str = "hub_1",
    detector_id: str = "station",
    train_id: str = "red_train",
) -> dict[str, object]:
    return {
        "id": rule_id,
        "enabled": enabled,
        "root": {
            "type": "train_detected",
            "hub_id": hub_id,
            "detector_id": detector_id,
            "train_id": train_id,
            "children": list(children),
        },
    }


def _speed(speed: object = 45, children: object = None) -> dict[str, object]:
    return {
        "type": "set_train_speed",
        "speed": speed,
        "children": [] if children is None else children,
    }


def test_parses_complete_nested_document(parser: AutomationParser) -> None:
    parsed = parser.parse(_document(_rule(
        {
            "type": "set_switch",
            "hub_id": "hub_1",
            "switch_id": "S1",
            "position": "straight",
            "children": [],
        },
        {
            "type": "wait",
            "seconds": 1,
            "children": [{
                "type": "on_count",
                "count": 5,
                "children": [_speed(-35)],
            }],
        },
    )))

    assert parsed.version == 1
    assert parsed.rules[0].trigger.train_id == "red_train"
    switch, wait = parsed.rules[0].children
    assert isinstance(switch.config, SetSwitchConfig)
    assert isinstance(wait.config, WaitConfig)
    count = wait.children[0]
    assert count.path == (1, 0)
    assert isinstance(count.config, OnCountConfig)
    assert isinstance(count.children[0].config, SetTrainSpeedConfig)


def test_parse_json_reports_syntax_location(parser: AutomationParser) -> None:
    with pytest.raises(
        AutomationParseError,
        match=r"^\$: invalid JSON at line 1, column",
    ):
        parser.parse_json('{"version": 1,}')


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            '{"version":1,"version":1,"rules":[]}',
            "duplicate field in JSON object: version",
        ),
        (
            '{"version":1,"rules":[],"value":NaN}',
            "non-standard numeric constant: NaN",
        ),
        (
            '{"version":1,"rules":[],"value":Infinity}',
            "non-standard numeric constant: Infinity",
        ),
    ],
)
def test_parse_json_rejects_non_standard_json(
    parser: AutomationParser,
    text: str,
    message: str,
) -> None:
    with pytest.raises(AutomationParseError, match=message):
        parser.parse_json(text)


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"version": 1}, r"\$: missing required field: rules"),
        ({"version": 1, "rules": [], "extra": True}, r"\$.extra: unknown"),
        ({"version": True, "rules": []}, r"\$.version: must be an integer"),
        ({"version": 3, "rules": []}, r"unsupported version: 3"),
        ({"version": 1, "rules": {}}, r"\$.rules: must be an array"),
    ],
)
def test_rejects_invalid_document_shape(
    parser: AutomationParser,
    document: object,
    message: str,
) -> None:
    with pytest.raises(AutomationParseError, match=message):
        parser.parse(document)


@pytest.mark.parametrize("value", ["", "  ", 7, None])
def test_rejects_invalid_rule_id(parser: AutomationParser, value: object) -> None:
    rule = _rule(_speed())
    rule["id"] = value
    with pytest.raises(AutomationParseError, match=r"\.id: must be a non-empty"):
        parser.parse(_document(rule))


def test_trims_identifiers(parser: AutomationParser) -> None:
    parsed = parser.parse(_document(_rule(
        _speed(),
        rule_id=" departure ",
        hub_id=" hub_1 ",
        detector_id=" station ",
        train_id=" red_train ",
    )))

    rule = parsed.rules[0]
    assert rule.id == "departure"
    assert (rule.trigger.hub_id, rule.trigger.detector_id, rule.trigger.train_id) == (
        "hub_1",
        "station",
        "red_train",
    )


def test_rejects_duplicate_rule_ids(parser: AutomationParser) -> None:
    with pytest.raises(AutomationParseError, match="duplicate rule id: duplicate"):
        parser.parse(_document(
            _rule(_speed(), rule_id="duplicate"),
            _rule(_speed(), rule_id="duplicate", detector_id="other"),
        ))


def test_rejects_duplicate_enabled_triggers(parser: AutomationParser) -> None:
    with pytest.raises(AutomationParseError, match="already used by rule: first"):
        parser.parse(_document(
            _rule(_speed(), rule_id="first"),
            _rule(_speed(), rule_id="second"),
        ))


def test_allows_duplicate_trigger_when_alternatives_are_disabled(
    parser: AutomationParser,
) -> None:
    parsed = parser.parse(_document(
        _rule(_speed(10), rule_id="first", enabled=False),
        _rule(_speed(20), rule_id="second", enabled=False),
    ))

    assert len(parsed.rules) == 2


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda root: root.update(type="wait"), r"\.root.type: must be train_detected"),
        (lambda root: root.update(extra=1), r"\.root.extra: unknown field"),
        (lambda root: root.update(children=[]), r"\.root.children: must not be empty"),
        (lambda root: root.update(children={}), r"\.root.children: must be an array"),
    ],
)
def test_rejects_invalid_root(
    parser: AutomationParser,
    mutate,
    message: str,
) -> None:
    rule = _rule(_speed())
    mutate(rule["root"])
    with pytest.raises(AutomationParseError, match=message):
        parser.parse(_document(rule))


@pytest.mark.parametrize(
    ("node", "message"),
    [
        (
            {"type": "unknown", "children": []},
            r"unsupported node type: unknown",
        ),
        (
            {"type": "train_detected", "children": []},
            r"train_detected is only allowed at a rule root",
        ),
        (
            {"type": "wait", "seconds": 1, "children": [], "extra": True},
            r"\.extra: unknown field",
        ),
        (
            {"type": "wait", "seconds": 1, "children": []},
            r"\.children: must not be empty",
        ),
        (
            _speed(20, [{"type": "unknown", "children": []}]),
            r"\.children: must be empty",
        ),
    ],
)
def test_rejects_invalid_node_shape(
    parser: AutomationParser,
    node: object,
    message: str,
) -> None:
    with pytest.raises(AutomationParseError, match=message):
        parser.parse(_document(_rule(node)))


@pytest.mark.parametrize("seconds", [-1, 3600.1, True, "1", float("inf")])
def test_rejects_invalid_wait(parser: AutomationParser, seconds: object) -> None:
    node = {"type": "wait", "seconds": seconds, "children": [_speed()]}
    with pytest.raises(AutomationParseError, match=r"\.seconds: must be"):
        parser.parse(_document(_rule(node)))


@pytest.mark.parametrize("count", [0, -1, True, 1.5])
def test_rejects_invalid_count(parser: AutomationParser, count: object) -> None:
    node = {
        "type": "on_count",
        "count": count,
        "children": [_speed()],
    }
    with pytest.raises(AutomationParseError, match=r"\.count: must be"):
        parser.parse(_document(_rule(node)))


def test_rejects_removed_count_mode(parser: AutomationParser) -> None:
    node = {
        "type": "on_count",
        "count": 1,
        "mode": "repeat",
        "children": [_speed()],
    }
    with pytest.raises(AutomationParseError, match=r"\.mode: unknown field"):
        parser.parse(_document(_rule(node)))


def test_parses_version_2_count_branches(parser: AutomationParser) -> None:
    node = {
        "type": "if_count",
        "count": 5,
        "children": [
            {
                "type": "branch",
                "when": "otherwise",
                "children": [_speed(10)],
            },
            {
                "type": "branch",
                "when": "match",
                "children": [_speed(50)],
            },
        ],
    }

    document = parser.parse(_document(_rule(node), version=2))

    count_node = document.rules[0].children[0]
    assert isinstance(count_node.config, IfCountConfig)
    assert count_node.config.otherwise_index == 0
    assert count_node.config.match_index == 1
    assert all(isinstance(child.config, BranchConfig) for child in count_node.children)


def test_rejects_version_2_node_in_version_1(parser: AutomationParser) -> None:
    node = {
        "type": "if_count",
        "count": 5,
        "children": [
            {"type": "branch", "when": "match", "children": [_speed()]},
            {"type": "branch", "when": "otherwise", "children": [_speed()]},
        ],
    }

    with pytest.raises(
        AutomationParseError,
        match=r"\.type: requires automation document version 2 or later",
    ):
        parser.parse(_document(_rule(node)))


@pytest.mark.parametrize(
    ("children", "message"),
    [
        ([], r"must not be empty"),
        (
            [{"type": "branch", "when": "match", "children": [_speed()]}],
            r"must contain exactly one match branch",
        ),
        (
            [
                {"type": "branch", "when": "match", "children": [_speed()]},
                {"type": "branch", "when": "match", "children": [_speed()]},
            ],
            r"duplicate match branch",
        ),
        (
            [
                _speed(),
                {"type": "branch", "when": "otherwise", "children": [_speed()]},
            ],
            r"\.type: must be branch",
        ),
    ],
)
def test_rejects_invalid_if_count_branches(
    parser: AutomationParser,
    children: list[object],
    message: str,
) -> None:
    node = {"type": "if_count", "count": 5, "children": children}
    with pytest.raises(AutomationParseError, match=message):
        parser.parse(_document(_rule(node), version=2))


def test_rejects_branch_outside_if_count(parser: AutomationParser) -> None:
    node = {"type": "branch", "when": "match", "children": [_speed()]}
    with pytest.raises(AutomationParseError, match=r"only allowed under: if_count"):
        parser.parse(_document(_rule(node), version=2))


@pytest.mark.parametrize("count", [0, -1, True, 1.5])
def test_rejects_invalid_if_count(parser: AutomationParser, count: object) -> None:
    node = {
        "type": "if_count",
        "count": count,
        "children": [
            {"type": "branch", "when": "match", "children": [_speed()]},
            {"type": "branch", "when": "otherwise", "children": [_speed()]},
        ],
    }
    with pytest.raises(AutomationParseError, match=r"\.count: must be"):
        parser.parse(_document(_rule(node), version=2))


@pytest.mark.parametrize("speed", [-101, 101, True, 1.5])
def test_rejects_invalid_speed(parser: AutomationParser, speed: object) -> None:
    with pytest.raises(AutomationParseError, match=r"\.speed: must be"):
        parser.parse(_document(_rule(_speed(speed))))


@pytest.mark.parametrize("position", ["left", 90, True])
def test_rejects_invalid_switch_position(
    parser: AutomationParser,
    position: object,
) -> None:
    node = {
        "type": "set_switch",
        "hub_id": "hub",
        "switch_id": "S1",
        "position": position,
        "children": [],
    }
    with pytest.raises(
        AutomationParseError,
        match=r"must be straight, diverge, or flip",
    ):
        parser.parse(_document(_rule(node)))


def test_accepts_flip_switch_position(parser: AutomationParser) -> None:
    node = {
        "type": "set_switch",
        "hub_id": "hub",
        "switch_id": "S1",
        "position": "flip",
        "children": [],
    }

    document = parser.parse(_document(_rule(node)))

    switch = document.rules[0].children[0]
    assert isinstance(switch.config, SetSwitchConfig)
    assert switch.config.position.value == "flip"


class _CustomFunction(NodeFunction):
    type = "custom"
    children_policy = ChildrenPolicy.FORBIDDEN
    fields = frozenset({"value"})

    def parse(self, value: Mapping[str, object], path: str) -> object:
        return value["value"]

    async def execute(
        self,
        context: FunctionContext,
        node: Node,
    ) -> NodeDecision:
        return NodeDecision.SKIP_CHILDREN


def test_registry_plugs_and_unplugs_custom_functions() -> None:
    registry = FunctionRegistry()
    parser = AutomationParser(registry)
    document = _document(_rule({"type": "custom", "value": 7, "children": []}))
    with pytest.raises(AutomationParseError, match="unsupported node type: custom"):
        parser.parse(document)

    function = _CustomFunction()
    registry.register(function)
    assert parser.parse(document).rules[0].children[0].config == 7
    assert registry.unregister("custom") is function
    with pytest.raises(AutomationParseError, match="unsupported node type: custom"):
        parser.parse(document)


def test_registry_rejects_duplicate_types() -> None:
    registry = FunctionRegistry([WaitFunction()])
    with pytest.raises(DuplicateFunctionError, match="already registered: wait"):
        registry.register(WaitFunction())


def test_registry_replaces_existing_binding() -> None:
    first = WaitFunction()
    second = WaitFunction()
    registry = FunctionRegistry([first])

    assert registry.replace(second) is first
    assert registry.get("wait") is second


@pytest.mark.parametrize(
    ("attribute", "value", "message"),
    [
        (
            "type",
            " custom ",
            "function type must be a non-empty string without surrounding "
            "whitespace",
        ),
        ("type", "train_detected", "function type is reserved: train_detected"),
        (
            "children_policy",
            "forbidden",
            "function custom has an invalid children policy",
        ),
        (
            "allowed_parent_types",
            {"if_count"},
            "allowed_parent_types must be None or a frozenset",
        ),
        (
            "minimum_document_version",
            True,
            "minimum_document_version must be a positive integer",
        ),
        (
            "fields",
            {"value"},
            "function custom fields must be a frozenset",
        ),
        (
            "fields",
            frozenset({"children"}),
            "function custom declares reserved field: children",
        ),
    ],
)
def test_registry_rejects_invalid_function_contract(
    attribute: str,
    value: object,
    message: str,
) -> None:
    function = _CustomFunction()
    setattr(function, attribute, value)

    with pytest.raises(ValueError, match=message):
        FunctionRegistry([function])


def test_rejects_tree_beyond_depth_limit() -> None:
    parser = AutomationParser(
        FunctionRegistry([WaitFunction(), SetTrainSpeedFunction(_set_speed)]),
        max_tree_depth=2,
    )
    tree = {
        "type": "wait",
        "seconds": 0,
        "children": [{
            "type": "wait",
            "seconds": 0,
            "children": [_speed()],
        }],
    }

    with pytest.raises(AutomationParseError, match="tree depth must not exceed 2"):
        parser.parse(_document(_rule(tree)))


def test_rejects_rule_beyond_node_limit() -> None:
    parser = AutomationParser(
        FunctionRegistry([SetTrainSpeedFunction(_set_speed)]),
        max_nodes_per_rule=2,
    )

    with pytest.raises(AutomationParseError, match="at most 2 nodes"):
        parser.parse(_document(_rule(_speed(1), _speed(2), _speed(3))))


def test_rejects_document_beyond_rule_limit(parser: AutomationParser) -> None:
    limited = AutomationParser(FunctionRegistry([SetTrainSpeedFunction(_set_speed)]), max_rules=1)

    with pytest.raises(AutomationParseError, match="at most 1 rules"):
        limited.parse(_document(
            _rule(_speed(), rule_id="first"),
            _rule(_speed(), rule_id="second", detector_id="other"),
        ))


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("max_rules", 0),
        ("max_nodes_per_rule", True),
        ("max_tree_depth", 1.5),
    ],
)
def test_rejects_invalid_parser_limits(argument: str, value: object) -> None:
    with pytest.raises(ValueError, match=f"{argument} must be a positive integer"):
        AutomationParser(FunctionRegistry(), **{argument: value})
