from __future__ import annotations

import math
from collections.abc import Mapping

from automation_tree.errors import AutomationParseError


def require_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AutomationParseError(path, "must be an object")
    for key in value:
        if not isinstance(key, str):
            raise AutomationParseError(path, "field names must be strings")
    return value


def require_fields(
    value: Mapping[str, object],
    *,
    required: set[str],
    allowed: set[str],
    path: str,
) -> None:
    missing = required - value.keys()
    if missing:
        name = sorted(missing)[0]
        raise AutomationParseError(path, f"missing required field: {name}")
    unknown = value.keys() - allowed
    if unknown:
        name = sorted(unknown)[0]
        raise AutomationParseError(f"{path}.{name}", "unknown field")


def require_non_empty_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AutomationParseError(path, "must be a non-empty string")
    return value.strip()


def require_bool(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise AutomationParseError(path, "must be a boolean")
    return value


def require_int(
    value: object,
    path: str,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AutomationParseError(path, "must be an integer")
    if value < minimum or maximum is not None and value > maximum:
        bounds = f"{minimum} or greater"
        if maximum is not None:
            bounds = f"in {minimum}..{maximum}"
        raise AutomationParseError(path, f"must be an integer {bounds}")
    return value


def require_finite_number(
    value: object,
    path: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AutomationParseError(path, "must be a number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or not minimum <= value <= maximum:
        raise AutomationParseError(
            path,
            f"must be a finite number in {minimum:g}..{maximum:g}",
        )
    return float(value)
