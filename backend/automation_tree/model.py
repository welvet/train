from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class Trigger:
    hub_id: str
    detector_id: str
    train_id: str


@dataclass(frozen=True, slots=True)
class Node:
    type: str
    config: object
    children: tuple[Node, ...]
    path: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    enabled: bool
    trigger: Trigger
    children: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class AutomationDocument:
    version: int
    rules: tuple[Rule, ...]


class RuleState(str, Enum):
    DISABLED = "disabled"
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"


@dataclass(frozen=True, slots=True)
class RuleStatus:
    rule_id: str
    state: RuleState
    last_error: str | None
    failure: NodeFailure | None


@dataclass(frozen=True, slots=True)
class NodeFailure:
    node_type: str
    node_path: tuple[int, ...]
    message: str
