"""Standalone parser and runner for configurable automation trees."""

from automation_tree.errors import AutomationParseError, DuplicateFunctionError
from automation_tree.functions import (
    BranchFunction,
    FunctionRegistry,
    IfCountFunction,
    OnCountFunction,
    SetSwitchFunction,
    SetTrainSpeedFunction,
    WaitFunction,
)
from automation_tree.model import (
    AutomationDocument,
    CURRENT_AUTOMATION_DOCUMENT_VERSION,
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
    "BranchFunction",
    "CURRENT_AUTOMATION_DOCUMENT_VERSION",
    "DuplicateFunctionError",
    "FunctionRegistry",
    "IfCountFunction",
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
