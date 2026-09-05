"""Standalone parser and runner for configurable automation trees."""

from automation_tree.errors import AutomationParseError, DuplicateFunctionError
from automation_tree.functions import (
    FunctionRegistry,
    OnCountFunction,
    SetSwitchFunction,
    SetTrainSpeedFunction,
    WaitFunction,
)
from automation_tree.model import (
    AutomationDocument,
    Node,
    NodeFailure,
    Rule,
    RuleState,
    RuleStatus,
    Trigger,
)
from automation_tree.parser import AutomationParser
from automation_tree.runner import AutomationRunner

__all__ = [
    "AutomationDocument",
    "AutomationParseError",
    "AutomationParser",
    "AutomationRunner",
    "DuplicateFunctionError",
    "FunctionRegistry",
    "Node",
    "NodeFailure",
    "OnCountFunction",
    "Rule",
    "RuleState",
    "RuleStatus",
    "SetSwitchFunction",
    "SetTrainSpeedFunction",
    "Trigger",
    "WaitFunction",
]
