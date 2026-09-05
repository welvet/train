from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import tempfile
from collections.abc import Callable, Iterable, Mapping, Set
from dataclasses import asdict
from pathlib import Path

from automation_tree import (
    AutomationDocument,
    AutomationParseError,
    AutomationParser,
    AutomationRunner,
    FunctionRegistry,
    OnCountFunction,
    SetSwitchFunction,
    SetTrainSpeedFunction,
    Trigger,
    WaitFunction,
)
from automation_tree.functions import (
    FunctionContext,
    SetSwitchConfig,
    SetTrainSpeedConfig,
)
from automation_tree.model import Node

from train.core.event_bus import CommandFailed, CommandResourceNotFound, EventBus
from train.core.module import Module
from train.domain import (
    AutomationHalt,
    AutomationResume,
    SetSwitchPosition,
    SetTrainSpeed,
    SwitchPositionChanged,
    SystemState,
    TagDetected,
    TrainSpeedChanged,
)

COMMAND_TIMEOUT = 3.0


class AutomationModule(Module):
    """Connect the configurable automation engine to the train runtime."""

    def __init__(
        self,
        bus: EventBus,
        *,
        path: Path,
        tagged_trains: Set[str],
    ) -> None:
        super().__init__(bus)
        self._path = path
        self._tagged_trains = frozenset(tagged_trains)
        self._parser, self._functions = create_automation_parser(
            set_switch=self._set_switch,
            set_train_speed=self._set_train_speed,
        )
        self._runner = AutomationRunner(
            self._functions,
            status_changed=self._notify_changed,
        )
        self._document_json: dict[str, object] = {"version": 1, "rules": []}
        self._replace_lock = asyncio.Lock()
        self._updates: set[asyncio.Task[dict[str, object]]] = set()
        self._started = False
        self._change_handlers: set[Callable[[], None]] = set()
        self._log = logging.getLogger("train.automation")

    async def start(self) -> None:
        document, document_json = load_automation_file(
            self._path,
            parser=self._parser,
            state=self.bus.state,
            tagged_trains=self._tagged_trains,
        )
        await self._runner.replace(document)
        if self.bus.state.automation.halted:
            await self._runner.pause()
        self.bus.subscribe(TagDetected, self._on_tag_detected)
        self.bus.subscribe(AutomationHalt, self._on_halt)
        self.bus.subscribe(AutomationResume, self._on_resume)
        self._document_json = document_json
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        for event_type, handler in (
            (TagDetected, self._on_tag_detected),
            (AutomationHalt, self._on_halt),
            (AutomationResume, self._on_resume),
        ):
            self.bus.unsubscribe(event_type, handler)
        if self._updates:
            await asyncio.gather(
                *(asyncio.shield(update) for update in tuple(self._updates)),
                return_exceptions=True,
            )
        async with self._replace_lock:
            await self._runner.close()

    @property
    def healthy(self) -> bool:
        return self._started

    def snapshot(self) -> dict[str, object]:
        return {
            "document": copy.deepcopy(self._document_json),
            "eligible_train_ids": sorted(self._tagged_trains),
            "paused": self._runner.paused,
            "statuses": [asdict(status) for status in self._runner.statuses()],
        }

    def subscribe_changes(self, handler: Callable[[], None]) -> None:
        self._change_handlers.add(handler)

    def unsubscribe_changes(self, handler: Callable[[], None]) -> None:
        self._change_handlers.discard(handler)

    async def replace_json(self, text: str) -> dict[str, object]:
        """Validate, persist, and activate a complete replacement document."""
        if not self._started:
            raise RuntimeError("automation module is not running")
        document = self._parser.parse_json(text)
        validate_automation_topology(
            document,
            state=self.bus.state,
            tagged_trains=self._tagged_trains,
        )
        raw_document = json.loads(text)
        if not isinstance(raw_document, dict):
            raise AutomationParseError("$", "must be an object")

        update: asyncio.Task[dict[str, object]] = asyncio.create_task(
            self._replace(document, raw_document),
            name="automation-replacement",
        )
        self._updates.add(update)
        update.add_done_callback(self._updates.discard)
        try:
            await asyncio.shield(update)
        except asyncio.CancelledError:
            await update
            raise
        return update.result()

    async def _replace(
        self,
        document: AutomationDocument,
        raw_document: dict[str, object],
    ) -> dict[str, object]:
        async with self._replace_lock:
            staged = _stage_document(self._path, raw_document)
            previous = self._runner.document
            previous_json = self._document_json
            try:
                _replace_document(staged, self._path)
                try:
                    await self._runner.replace(document, preserve_unchanged=False)
                except BaseException:
                    rollback = _stage_document(self._path, previous_json)
                    try:
                        _replace_document(rollback, self._path)
                    finally:
                        rollback.unlink(missing_ok=True)
                    await self._runner.replace(previous)
                    raise
                self._document_json = copy.deepcopy(raw_document)
            finally:
                staged.unlink(missing_ok=True)
            self._log.info(
                "Applied automation document with %d rule(s)", len(document.rules)
            )
            return self.snapshot()

    async def _on_tag_detected(self, event: TagDetected) -> None:
        await self._runner.trigger(Trigger(
            hub_id=event.hub_name,
            detector_id=event.detector_name,
            train_id=event.train_id,
        ))

    async def _on_halt(self, event: AutomationHalt) -> None:
        await self._runner.pause()
        self._log.info("Automation paused")

    async def _on_resume(self, event: AutomationResume) -> None:
        await self._runner.resume()
        self._log.info("Automation resumed")

    def _notify_changed(self) -> None:
        for handler in tuple(self._change_handlers):
            try:
                handler()
            except Exception:
                self._log.exception("Automation change handler failed")

    async def _set_train_speed(
        self,
        context: FunctionContext,
        config: SetTrainSpeedConfig,
    ) -> None:
        command = SetTrainSpeed(
            train_name=context.trigger.train_id,
            speed=config.speed,
        )
        try:
            result = await self.bus.dispatch(command, timeout=COMMAND_TIMEOUT)
        except (CommandFailed, CommandResourceNotFound) as exc:
            raise RuntimeError(
                f"train speed change failed: {context.trigger.train_id}"
            ) from exc
        if not isinstance(result, TrainSpeedChanged):
            raise RuntimeError("train speed command returned an invalid response")

    async def _set_switch(
        self,
        context: FunctionContext,
        config: SetSwitchConfig,
    ) -> None:
        command = SetSwitchPosition(
            hub_name=config.hub_id,
            switch_name=config.switch_id,
            target=config.position.value,
        )
        try:
            result = await self.bus.dispatch(command, timeout=COMMAND_TIMEOUT)
        except (CommandFailed, CommandResourceNotFound) as exc:
            raise RuntimeError(
                f"switch move failed: {config.hub_id}/{config.switch_id}"
            ) from exc
        if not isinstance(result, SwitchPositionChanged):
            raise RuntimeError("switch command returned an invalid response")


def load_automation_file(
    path: Path,
    *,
    parser: AutomationParser,
    state: SystemState,
    tagged_trains: Set[str],
) -> tuple[AutomationDocument, dict[str, object]]:
    try:
        text = path.read_text()
    except FileNotFoundError as exc:
        raise AutomationParseError(
            "$", f"missing {path}; create the workspace with 'tools/data init'"
        ) from exc
    document = parser.parse_json(text)
    validate_automation_topology(
        document,
        state=state,
        tagged_trains=tagged_trains,
    )
    raw_document = json.loads(text)
    if not isinstance(raw_document, dict):
        raise AutomationParseError("$", "must be an object")
    return document, raw_document


def create_automation_parser(
    *,
    set_switch=None,
    set_train_speed=None,
) -> tuple[AutomationParser, FunctionRegistry]:
    functions = FunctionRegistry([
        OnCountFunction(),
        SetSwitchFunction(set_switch or _unavailable_handler),
        SetTrainSpeedFunction(set_train_speed or _unavailable_handler),
        WaitFunction(),
    ])
    return AutomationParser(functions), functions


def validate_automation_topology(
    document: AutomationDocument,
    *,
    state: SystemState,
    tagged_trains: Set[str],
) -> None:
    for rule_index, rule in enumerate(document.rules):
        root_path = f"$.rules[{rule_index}].root"
        if rule.trigger.train_id not in state.trains:
            raise AutomationParseError(
                f"{root_path}.train_id",
                f"unknown train: {rule.trigger.train_id}",
            )
        if rule.trigger.train_id not in tagged_trains:
            raise AutomationParseError(
                f"{root_path}.train_id",
                f"train has no tag_id: {rule.trigger.train_id}",
            )
        hub = state.arduino_hubs.get(rule.trigger.hub_id)
        if hub is None:
            raise AutomationParseError(
                f"{root_path}.hub_id",
                f"unknown Arduino hub: {rule.trigger.hub_id}",
            )
        if rule.trigger.detector_id not in hub.detectors:
            raise AutomationParseError(
                f"{root_path}.detector_id",
                "unknown detector: "
                f"{rule.trigger.hub_id}/{rule.trigger.detector_id}",
            )
        for node in _walk_nodes(rule.children):
            if not isinstance(node.config, SetSwitchConfig):
                continue
            switch_hub = state.arduino_hubs.get(node.config.hub_id)
            node_path = root_path + "".join(
                f".children[{index}]" for index in node.path
            )
            if switch_hub is None:
                raise AutomationParseError(
                    f"{node_path}.hub_id",
                    f"unknown Arduino hub: {node.config.hub_id}",
                )
            if node.config.switch_id not in switch_hub.switches:
                raise AutomationParseError(
                    f"{node_path}.switch_id",
                    f"unknown switch: {node.config.hub_id}/{node.config.switch_id}",
                )


def _walk_nodes(nodes: Iterable[Node]):
    for node in nodes:
        yield node
        yield from _walk_nodes(node.children)


def _stage_document(path: Path, document: Mapping[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    staged = Path(name)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(document, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return staged


def _replace_document(staged: Path, destination: Path) -> None:
    os.replace(staged, destination)
    directory = os.open(destination.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


async def _unavailable_handler(*args: object) -> None:
    raise RuntimeError("automation command handler is unavailable")
