from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from automation_tree.errors import AutomationParseError
from automation_tree.validation import require_int, require_non_empty_string

MIN_SIGNAL_VALUE = -(2**53 - 1)
MAX_SIGNAL_VALUE = 2**53 - 1


class SignalOperator(str, Enum):
    EQ = "eq"
    NOT_EQ = "not_eq"
    LESS = "less"
    MORE = "more"


@dataclass(frozen=True, slots=True)
class SignalCondition:
    signal: str
    operator: SignalOperator
    value: int

    def matches(self, actual: int) -> bool:
        if self.operator is SignalOperator.EQ:
            return actual == self.value
        if self.operator is SignalOperator.NOT_EQ:
            return actual != self.value
        if self.operator is SignalOperator.LESS:
            return actual < self.value
        return actual > self.value


def parse_signal_condition(
    value: Mapping[str, object],
    path: str,
) -> SignalCondition:
    try:
        operator = SignalOperator(value["operator"])
    except (TypeError, ValueError) as exc:
        raise AutomationParseError(
            f"{path}.operator",
            "must be eq, not_eq, less, or more",
        ) from exc
    return SignalCondition(
        signal=require_non_empty_string(value["signal"], f"{path}.signal"),
        operator=operator,
        value=require_int(
            value["value"],
            f"{path}.value",
            minimum=MIN_SIGNAL_VALUE,
            maximum=MAX_SIGNAL_VALUE,
        ),
    )
