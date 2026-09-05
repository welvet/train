from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from automation_tree.functions import FunctionContext, FunctionRegistry, NodeDecision
from automation_tree.model import (
    AutomationDocument,
    Node,
    NodeFailure,
    Rule,
    RuleState,
    RuleStatus,
    Trigger,
)

Sleep = Callable[[float], Awaitable[None]]


@dataclass(slots=True)
class _RuntimeRule:
    definition: Rule
    counters: dict[tuple[int, ...], int] = field(default_factory=dict)
    state: RuleState = RuleState.IDLE
    task: asyncio.Task[None] | None = None
    last_error: str | None = None
    failure: NodeFailure | None = None

    def __post_init__(self) -> None:
        if not self.definition.enabled:
            self.state = RuleState.DISABLED


class _ExecutionContext(FunctionContext):
    def __init__(
        self,
        runner: AutomationRunner,
        runtime: _RuntimeRule,
    ) -> None:
        self._runner = runner
        self._runtime = runtime

    @property
    def rule_id(self) -> str:
        return self._runtime.definition.id

    @property
    def trigger(self) -> Trigger:
        return self._runtime.definition.trigger

    async def sleep(self, seconds: float) -> None:
        self._runtime.state = RuleState.WAITING
        try:
            await self._runner._sleep(seconds)
        finally:
            if self._runtime.task is asyncio.current_task():
                self._runtime.state = RuleState.RUNNING

    def next_count(self, path: tuple[int, ...]) -> int:
        occurrence = self._runtime.counters.get(path, 0) + 1
        self._runtime.counters[path] = occurrence
        return occurrence


class AutomationRunner:
    """Concurrent, reconfigurable executor for parsed automation rules."""

    def __init__(
        self,
        functions: FunctionRegistry,
        *,
        sleep: Sleep = asyncio.sleep,
        logger: logging.Logger | None = None,
    ) -> None:
        self._functions = functions
        self._sleep = sleep
        self._log = logger or logging.getLogger("automation_tree")
        self._rules: dict[str, _RuntimeRule] = {}
        self._triggers: dict[Trigger, _RuntimeRule] = {}
        self._document = AutomationDocument(version=1, rules=())
        self._lock = asyncio.Lock()
        self._paused = False
        self._closed = False
        self._replacement_generation = 0
        self._replacements_pending = 0

    @property
    def document(self) -> AutomationDocument:
        return self._document

    @property
    def paused(self) -> bool:
        return self._paused

    def statuses(self) -> tuple[RuleStatus, ...]:
        return tuple(
            RuleStatus(
                rule_id=rule.id,
                state=self._rules[rule.id].state,
                last_error=self._rules[rule.id].last_error,
                failure=self._rules[rule.id].failure,
            )
            for rule in self._document.rules
        )

    async def replace(self, document: AutomationDocument) -> None:
        """Atomically replace configuration while preserving unchanged rules."""
        self._ensure_open()
        self._replacement_generation += 1
        self._replacements_pending += 1
        try:
            async with self._lock:
                self._ensure_open()
                self._validate_functions(document)
                definitions = {rule.id: rule for rule in document.rules}
                changing = [
                    runtime
                    for rule_id, runtime in self._rules.items()
                    if definitions.get(rule_id) != runtime.definition
                ]
                await self._cancel(changing)

                rules: dict[str, _RuntimeRule] = {}
                for definition in document.rules:
                    existing = self._rules.get(definition.id)
                    if existing is not None and existing.definition == definition:
                        rules[definition.id] = existing
                    else:
                        rules[definition.id] = _RuntimeRule(definition)

                self._rules = rules
                self._triggers = {
                    runtime.definition.trigger: runtime
                    for runtime in rules.values()
                    if runtime.definition.enabled
                }
                self._document = document
        finally:
            self._replacements_pending -= 1

    async def trigger(self, trigger: Trigger) -> str | None:
        """Admit a matching idle rule and return immediately with its ID."""
        generation = self._replacement_generation
        if self._replacements_pending or self._paused:
            return None
        async with self._lock:
            self._ensure_open()
            if (
                self._replacements_pending
                or generation != self._replacement_generation
                or self._paused
            ):
                return None
            runtime = self._triggers.get(trigger)
            if runtime is None or runtime.task is not None:
                return None
            runtime.state = RuleState.RUNNING
            runtime.last_error = None
            runtime.failure = None
            task = asyncio.create_task(
                self._execute(runtime),
                name=f"automation:{runtime.definition.id}",
            )
            runtime.task = task
            return runtime.definition.id

    async def pause(self) -> None:
        """Cancel active executions while preserving occurrence counters."""
        async with self._lock:
            self._ensure_open()
            self._paused = True
            await self._cancel(list(self._rules.values()))

    async def resume(self) -> None:
        async with self._lock:
            self._ensure_open()
            self._paused = False

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                await self._cancel(list(self._rules.values()))
            finally:
                self._triggers.clear()

    async def wait_idle(self) -> None:
        """Wait for executions that are active at the time of each snapshot."""
        while True:
            tasks = [
                runtime.task
                for runtime in self._rules.values()
                if runtime.task is not None
            ]
            if not tasks:
                return
            await asyncio.gather(
                *(asyncio.shield(task) for task in tasks),
                return_exceptions=True,
            )

    async def _execute(self, runtime: _RuntimeRule) -> None:
        task = asyncio.current_task()
        context = _ExecutionContext(self, runtime)
        try:
            await self._execute_children(context, runtime.definition.children)
        except asyncio.CancelledError:
            raise
        except _NodeExecutionError as exc:
            runtime.last_error = str(exc) or type(exc).__name__
            runtime.failure = NodeFailure(
                node_type=exc.node.type,
                node_path=exc.node.path,
                message=runtime.last_error,
            )
            self._log.error(
                "Automation rule %s failed at %s node %s: %s",
                runtime.definition.id,
                _format_node_path(exc.node.path),
                exc.node.type,
                exc,
                exc_info=True,
            )
        finally:
            if runtime.task is task:
                runtime.task = None
                runtime.state = (
                    RuleState.IDLE
                    if runtime.definition.enabled
                    else RuleState.DISABLED
                )

    async def _execute_children(
        self,
        context: _ExecutionContext,
        children: tuple[Node, ...],
    ) -> None:
        for node in children:
            function = self._functions.get(node.type)
            if function is None:
                raise _NodeExecutionError(
                    node,
                    RuntimeError(f"function is not registered: {node.type}"),
                )
            try:
                decision = await function.execute(context, node)
                if not isinstance(decision, NodeDecision):
                    raise TypeError(
                        f"function {node.type} returned invalid decision: {decision!r}"
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise _NodeExecutionError(node, exc) from exc
            if decision is NodeDecision.ENTER_CHILDREN:
                await self._execute_children(context, node.children)

    async def _cancel(self, runtimes: list[_RuntimeRule]) -> None:
        tasks: list[asyncio.Task[None]] = []
        for runtime in runtimes:
            if runtime.task is not None:
                runtime.task.cancel()
                tasks.append(runtime.task)
        if tasks:
            completion = asyncio.gather(*tasks, return_exceptions=True)
            try:
                await asyncio.shield(completion)
            except asyncio.CancelledError:
                await completion
                raise

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("automation runner is closed")

    def _validate_functions(self, document: AutomationDocument) -> None:
        missing = sorted({
            node.type
            for rule in document.rules
            for node in _walk_nodes(rule.children)
            if self._functions.get(node.type) is None
        })
        if missing:
            raise ValueError(f"functions are not registered: {', '.join(missing)}")


class _NodeExecutionError(Exception):
    def __init__(self, node: Node, cause: Exception) -> None:
        self.node = node
        self.cause = cause
        super().__init__(str(cause) or type(cause).__name__)


def _walk_nodes(children: tuple[Node, ...]):
    for node in children:
        yield node
        yield from _walk_nodes(node.children)


def _format_node_path(path: tuple[int, ...]) -> str:
    return "root" + "".join(f".children[{index}]" for index in path)
