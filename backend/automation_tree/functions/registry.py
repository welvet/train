from __future__ import annotations

from collections.abc import Iterable, Iterator

from automation_tree.errors import DuplicateFunctionError
from automation_tree.functions.base import ChildrenPolicy, NodeFunction


_RESERVED_NODE_TYPES = frozenset({"train_detected"})
_RESERVED_FIELDS = frozenset({"type", "children"})


class FunctionRegistry:
    """Collection used to plug node functions into a parser and runner.

    Replacing a function changes future node dispatches, including for documents
    that were already parsed. Callers should pause a runner before mutating its
    registry when swapping adapters must not overlap an active execution.
    """

    def __init__(self, functions: Iterable[NodeFunction] = ()) -> None:
        self._functions: dict[str, NodeFunction] = {}
        for function in functions:
            self.register(function)

    def register(self, function: NodeFunction) -> None:
        self._validate(function)
        if function.type in self._functions:
            raise DuplicateFunctionError(
                f"function is already registered: {function.type}"
            )
        self._functions[function.type] = function

    def unregister(self, function_type: str) -> NodeFunction:
        try:
            return self._functions.pop(function_type)
        except KeyError as exc:
            raise KeyError(f"function is not registered: {function_type}") from exc

    def replace(self, function: NodeFunction) -> NodeFunction:
        """Replace an existing function and return the previous binding."""
        self._validate(function)
        if function.type not in self._functions:
            raise KeyError(f"function is not registered: {function.type}")
        previous = self._functions[function.type]
        self._functions[function.type] = function
        return previous

    def get(self, function_type: str) -> NodeFunction | None:
        return self._functions.get(function_type)

    def __iter__(self) -> Iterator[NodeFunction]:
        return iter(self._functions.values())

    @staticmethod
    def _validate(function: NodeFunction) -> None:
        function_type = function.type
        if (
            not isinstance(function_type, str)
            or not function_type
            or function_type != function_type.strip()
        ):
            raise ValueError(
                "function type must be a non-empty string without "
                "surrounding whitespace"
            )
        if function_type in _RESERVED_NODE_TYPES:
            raise ValueError(f"function type is reserved: {function_type}")
        if not isinstance(function.children_policy, ChildrenPolicy):
            raise ValueError(
                f"function {function_type} has an invalid children policy"
            )
        if not isinstance(function.fields, frozenset) or any(
            not isinstance(field, str)
            or not field
            or field != field.strip()
            for field in function.fields
        ):
            raise ValueError(
                f"function {function_type} fields must be a frozenset of "
                "non-empty strings without surrounding whitespace"
            )
        reserved_fields = sorted(function.fields & _RESERVED_FIELDS)
        if reserved_fields:
            raise ValueError(
                f"function {function_type} declares reserved field: "
                f"{reserved_fields[0]}"
            )
