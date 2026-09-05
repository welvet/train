from __future__ import annotations


class AutomationParseError(ValueError):
    """Raised when an automation document does not match the supported schema."""

    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


class DuplicateFunctionError(ValueError):
    """Raised when two functions use the same node type."""
