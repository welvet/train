from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol, TypeVar

if TYPE_CHECKING:
    from automation_tree.model import Node, Trigger


ConfigT = TypeVar("ConfigT")


class ChildrenPolicy(str, Enum):
    REQUIRED = "required"
    FORBIDDEN = "forbidden"


class NodeDecision(str, Enum):
    ENTER_CHILDREN = "enter_children"
    SKIP_CHILDREN = "skip_children"


@dataclass(frozen=True, slots=True)
class ChildSelection:
    """Select exactly one direct child of the executing node."""

    index: int


class FunctionContext(Protocol):
    @property
    def rule_id(self) -> str: ...

    @property
    def trigger(self) -> Trigger: ...

    async def sleep(self, seconds: float) -> None: ...

    def next_count(self, path: tuple[int, ...]) -> int: ...


class NodeFunction(ABC):
    """A parseable and executable automation node type.

    One registered instance can execute concurrently for different rules. Function
    implementations must therefore be stateless or otherwise safe for concurrent
    calls. Parsed configuration values must be immutable and implement value
    equality so formatting-only document replacements remain semantically equal.
    """

    type: str
    children_policy: ChildrenPolicy
    fields: frozenset[str]
    allowed_parent_types: frozenset[str] | None = None
    minimum_document_version: int = 1

    @abstractmethod
    def parse(self, value: Mapping[str, object], path: str) -> object:
        """Validate and return an immutable node-specific configuration."""

    @abstractmethod
    async def execute(
        self,
        context: FunctionContext,
        node: Node,
    ) -> NodeDecision | ChildSelection:
        """Execute the node and decide whether traversal enters or selects children."""


def require_node_config(node: Node, config_type: type[ConfigT]) -> ConfigT:
    if not isinstance(node.config, config_type):
        raise TypeError(
            f"{node.type} node requires {config_type.__name__}, "
            f"got {type(node.config).__name__}"
        )
    return node.config
