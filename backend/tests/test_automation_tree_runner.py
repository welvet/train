from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from automation_tree import (
    AutomationParser,
    AutomationRunner,
    BranchFunction,
    FunctionRegistry,
    IfCountFunction,
    OnCountFunction,
    RuleState,
    SetSwitchFunction,
    SetTrainSpeedFunction,
    Trigger,
    WaitFunction,
)
from automation_tree.functions import (
    ChildrenPolicy,
    ChildSelection,
    FunctionContext,
    NodeDecision,
    NodeFunction,
    SetSwitchConfig,
    SetTrainSpeedConfig,
)
from automation_tree.model import Node


TRIGGER = Trigger("hub", "station", "red")


class _Actions:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.block_speed: asyncio.Event | None = None
        self.speed_started = asyncio.Event()
        self.fail_speed: Exception | None = None

    async def set_speed(
        self,
        context: FunctionContext,
        config: SetTrainSpeedConfig,
    ) -> None:
        self.calls.append(("speed", context.rule_id, context.trigger, config.speed))
        self.speed_started.set()
        if self.fail_speed is not None:
            raise self.fail_speed
        if self.block_speed is not None:
            await self.block_speed.wait()

    async def set_switch(
        self,
        context: FunctionContext,
        config: SetSwitchConfig,
    ) -> None:
        self.calls.append((
            "switch",
            context.rule_id,
            config.hub_id,
            config.switch_id,
            config.position.value,
        ))


def _document(
    *children: object,
    enabled: bool = True,
    rule_id: str = "departure",
    detector_id: str = "station",
    version: int = 1,
) -> dict[str, object]:
    return {
        "version": version,
        "rules": [{
            "id": rule_id,
            "enabled": enabled,
            "root": {
                "type": "train_detected",
                "hub_id": "hub",
                "detector_id": detector_id,
                "train_id": "red",
                "children": list(children),
            },
        }],
    }


def _speed(speed: int) -> dict[str, object]:
    return {"type": "set_train_speed", "speed": speed, "children": []}


def _count(
    count: int,
    *children: object,
) -> dict[str, object]:
    return {
        "type": "on_count",
        "count": count,
        "children": list(children),
    }


def _wait(seconds: float, *children: object) -> dict[str, object]:
    return {"type": "wait", "seconds": seconds, "children": list(children)}


def _if_count(
    count: int,
    *,
    match: tuple[object, ...],
    otherwise: tuple[object, ...],
) -> dict[str, object]:
    return {
        "type": "if_count",
        "count": count,
        "children": [
            {"type": "branch", "when": "match", "children": list(match)},
            {
                "type": "branch",
                "when": "otherwise",
                "children": list(otherwise),
            },
        ],
    }


def _functions(actions: _Actions) -> FunctionRegistry:
    return FunctionRegistry([
        BranchFunction(),
        IfCountFunction(),
        WaitFunction(),
        OnCountFunction(),
        SetTrainSpeedFunction(actions.set_speed),
        SetSwitchFunction(actions.set_switch),
    ])


def _parser(actions: _Actions) -> AutomationParser:
    return AutomationParser(_functions(actions))


async def _run_once(runner: AutomationRunner) -> str | None:
    admitted = await runner.trigger(TRIGGER)
    await runner.wait_idle()
    return admitted


async def test_executes_children_in_order_and_passes_root_context() -> None:
    actions = _Actions()
    parser = _parser(actions)
    runner = AutomationRunner(_functions(actions))
    await runner.replace(parser.parse(_document(
        {
            "type": "set_switch",
            "hub_id": "hub",
            "switch_id": "S1",
            "position": "straight",
            "children": [],
        },
        _speed(45),
    )))

    assert await _run_once(runner) == "departure"
    assert actions.calls == [
        ("switch", "departure", "hub", "S1", "straight"),
        ("speed", "departure", TRIGGER, 45),
    ]


async def test_trigger_returns_without_waiting_for_execution() -> None:
    actions = _Actions()
    actions.block_speed = asyncio.Event()
    runner = AutomationRunner(_functions(actions))
    await runner.replace(_parser(actions).parse(_document(_speed(20))))

    assert await runner.trigger(TRIGGER) == "departure"
    await asyncio.wait_for(actions.speed_started.wait(), timeout=1)
    assert runner.statuses()[0].state is RuleState.RUNNING
    actions.block_speed.set()
    await runner.wait_idle()


async def test_cancelling_wait_idle_does_not_cancel_execution() -> None:
    actions = _Actions()
    actions.block_speed = asyncio.Event()
    runner = AutomationRunner(_functions(actions))
    await runner.replace(_parser(actions).parse(_document(_speed(20))))
    await runner.trigger(TRIGGER)
    await asyncio.wait_for(actions.speed_started.wait(), timeout=1)

    waiter = asyncio.create_task(runner.wait_idle())
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    assert runner.statuses()[0].state is RuleState.RUNNING
    assert await runner.trigger(TRIGGER) is None
    actions.block_speed.set()
    await runner.wait_idle()


async def test_ignores_unknown_disabled_and_active_rules() -> None:
    actions = _Actions()
    actions.block_speed = asyncio.Event()
    parser = _parser(actions)
    runner = AutomationRunner(_functions(actions))
    await runner.replace(parser.parse(_document(_speed(20))))

    assert await runner.trigger(Trigger("hub", "other", "red")) is None
    assert await runner.trigger(TRIGGER) == "departure"
    assert await runner.trigger(TRIGGER) is None
    actions.block_speed.set()
    await runner.wait_idle()

    await runner.replace(parser.parse(_document(_speed(20), enabled=False)))
    assert await runner.trigger(TRIGGER) is None
    assert runner.statuses()[0].state is RuleState.DISABLED


async def test_different_rules_run_concurrently() -> None:
    actions = _Actions()
    actions.block_speed = asyncio.Event()
    parser = _parser(actions)
    first = _document(_speed(10))["rules"][0]
    second = _document(
        _speed(20), rule_id="other", detector_id="yard"
    )["rules"][0]
    runner = AutomationRunner(_functions(actions))
    await runner.replace(parser.parse({"version": 1, "rules": [first, second]}))

    assert await runner.trigger(TRIGGER) == "departure"
    assert await runner.trigger(Trigger("hub", "yard", "red")) == "other"
    await asyncio.sleep(0)
    assert len(actions.calls) == 2
    actions.block_speed.set()
    await runner.wait_idle()


async def test_wait_marks_rule_waiting_and_delays_children() -> None:
    actions = _Actions()
    sleep_started = asyncio.Event()
    release_sleep = asyncio.Event()
    durations: list[float] = []

    async def sleep(seconds: float) -> None:
        durations.append(seconds)
        sleep_started.set()
        await release_sleep.wait()

    runner = AutomationRunner(_functions(actions), sleep=sleep)
    await runner.replace(_parser(actions).parse(_document(_wait(2.5, _speed(30)))))

    await runner.trigger(TRIGGER)
    await asyncio.wait_for(sleep_started.wait(), timeout=1)
    assert durations == [2.5]
    assert runner.statuses()[0].state is RuleState.WAITING
    assert actions.calls == []
    release_sleep.set()
    await runner.wait_idle()
    assert actions.calls[-1][-1] == 30
    assert runner.statuses()[0].state is RuleState.IDLE


async def test_occurrence_count_repeats() -> None:
    actions = _Actions()
    runner = AutomationRunner(_functions(actions))
    await runner.replace(_parser(actions).parse(
        _document(_count(3, _speed(3)))
    ))

    for _ in range(9):
        assert await _run_once(runner) == "departure"

    assert [call[-1] for call in actions.calls] == [3, 3, 3]


async def test_if_count_selects_exactly_one_branch_per_visit() -> None:
    actions = _Actions()
    runner = AutomationRunner(_functions(actions))
    await runner.replace(_parser(actions).parse(_document(
        _if_count(5, match=(_speed(50),), otherwise=(_speed(10),)),
        version=2,
    )))

    for _ in range(10):
        await _run_once(runner)

    assert [call[-1] for call in actions.calls] == [
        10, 10, 10, 10, 50,
        10, 10, 10, 10, 50,
    ]


async def test_if_count_branch_runs_multiple_children_in_order() -> None:
    actions = _Actions()
    runner = AutomationRunner(_functions(actions))
    await runner.replace(_parser(actions).parse(_document(
        _if_count(
            2,
            match=(_speed(20), _speed(21)),
            otherwise=(_speed(10), _speed(11)),
        ),
        version=2,
    )))

    await _run_once(runner)
    await _run_once(runner)

    assert [call[-1] for call in actions.calls] == [10, 11, 20, 21]


async def test_nested_if_count_counts_only_visits_that_reach_it() -> None:
    actions = _Actions()
    runner = AutomationRunner(_functions(actions))
    await runner.replace(_parser(actions).parse(_document(
        _count(
            2,
            _if_count(2, match=(_speed(20),), otherwise=(_speed(10),)),
        ),
        version=2,
    )))

    for _ in range(4):
        await _run_once(runner)

    assert [call[-1] for call in actions.calls] == [10, 20]


async def test_if_count_consumes_occurrence_when_selected_branch_fails() -> None:
    actions = _Actions()
    actions.fail_speed = RuntimeError("failed")
    runner = AutomationRunner(_functions(actions))
    document = _parser(actions).parse(_document(
        _if_count(2, match=(_speed(20),), otherwise=(_speed(10),)),
        version=2,
    ))
    await runner.replace(document)

    await _run_once(runner)
    actions.fail_speed = None
    await _run_once(runner)

    assert [call[-1] for call in actions.calls] == [10, 20]


async def test_if_count_counter_resets_on_complete_replacement() -> None:
    actions = _Actions()
    runner = AutomationRunner(_functions(actions))
    document = _parser(actions).parse(_document(
        _if_count(2, match=(_speed(20),), otherwise=(_speed(10),)),
        version=2,
    ))
    await runner.replace(document)
    await _run_once(runner)

    await runner.replace(document, preserve_unchanged=False)
    await _run_once(runner)

    assert [call[-1] for call in actions.calls] == [10, 10]


async def test_nested_counters_are_private_to_node_paths() -> None:
    actions = _Actions()
    runner = AutomationRunner(_functions(actions))
    await runner.replace(_parser(actions).parse(_document(
        _count(2, _speed(20)),
        _count(3, _speed(30)),
    )))

    for _ in range(6):
        await _run_once(runner)

    assert [call[-1] for call in actions.calls] == [20, 30, 20, 20, 30]


async def test_failure_stops_remaining_tree_and_rule_recovers() -> None:
    actions = _Actions()
    actions.fail_speed = RuntimeError("motor unavailable")
    runner = AutomationRunner(_functions(actions))
    await runner.replace(_parser(actions).parse(_document(_speed(10), _speed(20))))

    await _run_once(runner)
    assert [call[-1] for call in actions.calls] == [10]
    status = runner.statuses()[0]
    assert status.state is RuleState.IDLE
    assert status.last_error == "motor unavailable"
    assert status.failure is not None
    assert status.failure.node_type == "set_train_speed"
    assert status.failure.node_path == (0,)

    actions.fail_speed = None
    await _run_once(runner)
    assert [call[-1] for call in actions.calls] == [10, 10, 20]
    assert runner.statuses()[0].last_error is None
    assert runner.statuses()[0].failure is None


async def test_qualifying_count_is_consumed_when_child_fails() -> None:
    actions = _Actions()
    actions.fail_speed = RuntimeError("failed")
    runner = AutomationRunner(_functions(actions))
    await runner.replace(_parser(actions).parse(
        _document(_count(2, _speed(20)))
    ))

    await _run_once(runner)
    await _run_once(runner)
    actions.fail_speed = None
    await _run_once(runner)
    await _run_once(runner)

    assert [call[-1] for call in actions.calls] == [20, 20]


async def test_pause_cancels_execution_and_preserves_counters() -> None:
    actions = _Actions()
    sleep_started = asyncio.Event()
    sleep_calls = 0

    async def sleep(seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        sleep_started.set()
        if sleep_calls == 1:
            await asyncio.Event().wait()

    runner = AutomationRunner(_functions(actions), sleep=sleep)
    await runner.replace(_parser(actions).parse(_document(
        _count(2, _wait(10, _speed(20)))
    )))
    await _run_once(runner)
    await runner.trigger(TRIGGER)
    await asyncio.wait_for(sleep_started.wait(), timeout=1)

    await runner.pause()
    assert runner.paused
    assert runner.statuses()[0].state is RuleState.IDLE
    assert await runner.trigger(TRIGGER) is None
    await runner.resume()
    await _run_once(runner)
    await _run_once(runner)

    assert sleep_calls == 2
    assert [call[-1] for call in actions.calls] == [20]


async def test_disable_then_enable_resets_counters() -> None:
    actions = _Actions()
    parser = _parser(actions)
    runner = AutomationRunner(_functions(actions))
    enabled = parser.parse(_document(_count(2, _speed(20))))
    await runner.replace(enabled)
    await _run_once(runner)

    await runner.replace(parser.parse(_document(
        _count(2, _speed(20)), enabled=False
    )))
    await runner.replace(enabled)
    await _run_once(runner)
    assert actions.calls == []
    await _run_once(runner)
    assert [call[-1] for call in actions.calls] == [20]


async def test_semantically_unchanged_replace_keeps_counters() -> None:
    actions = _Actions()
    parser = _parser(actions)
    runner = AutomationRunner(_functions(actions))
    first = parser.parse_json(
        '{"version":1,"rules":[{"id":"departure","enabled":true,'
        '"root":{"type":"train_detected","hub_id":"hub",'
        '"detector_id":"station","train_id":"red","children":['
        '{"type":"on_count","count":2,"children":['
        '{"type":"set_train_speed","speed":20,"children":[]}]}]}}]}'
    )
    formatted = parser.parse(_document(_count(2, _speed(20))))
    await runner.replace(first)
    await _run_once(runner)
    await runner.replace(formatted)
    await _run_once(runner)

    assert [call[-1] for call in actions.calls] == [20]


async def test_changed_replace_cancels_old_execution_and_resets_state() -> None:
    actions = _Actions()
    sleep_started = asyncio.Event()
    cancelled = asyncio.Event()

    async def sleep(seconds: float) -> None:
        sleep_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    parser = _parser(actions)
    runner = AutomationRunner(_functions(actions), sleep=sleep)
    await runner.replace(parser.parse(_document(_wait(10, _speed(10)))))
    await runner.trigger(TRIGGER)
    await asyncio.wait_for(sleep_started.wait(), timeout=1)

    await runner.replace(parser.parse(_document(_speed(30))))
    assert cancelled.is_set()
    await _run_once(runner)
    assert [call[-1] for call in actions.calls] == [30]


async def test_detection_during_replacement_is_dropped_not_queued() -> None:
    actions = _Actions()
    sleep_started = asyncio.Event()
    cancelling = asyncio.Event()
    finish_cleanup = asyncio.Event()

    async def sleep(seconds: float) -> None:
        sleep_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelling.set()
            await finish_cleanup.wait()
            raise

    functions = _functions(actions)
    parser = AutomationParser(functions)
    runner = AutomationRunner(functions, sleep=sleep)
    await runner.replace(parser.parse(_document(_wait(10, _speed(10)))))
    await runner.trigger(TRIGGER)
    await asyncio.wait_for(sleep_started.wait(), timeout=1)

    replacement = asyncio.create_task(
        runner.replace(parser.parse(_document(_speed(30))))
    )
    await asyncio.wait_for(cancelling.wait(), timeout=1)
    assert await asyncio.wait_for(runner.trigger(TRIGGER), timeout=0.1) is None

    finish_cleanup.set()
    await replacement
    assert await _run_once(runner) == "departure"
    assert [call[-1] for call in actions.calls] == [30]


async def test_unchanged_active_rule_survives_other_rule_replacement() -> None:
    actions = _Actions()
    actions.block_speed = asyncio.Event()
    parser = _parser(actions)
    first = _document(_speed(10))["rules"][0]
    old_second = _document(
        _speed(20), rule_id="other", detector_id="yard"
    )["rules"][0]
    runner = AutomationRunner(_functions(actions))
    await runner.replace(parser.parse({"version": 1, "rules": [first, old_second]}))
    await runner.trigger(TRIGGER)
    await asyncio.wait_for(actions.speed_started.wait(), timeout=1)

    new_second = _document(
        _speed(30), rule_id="other", detector_id="yard"
    )["rules"][0]
    await runner.replace(parser.parse({"version": 1, "rules": [first, new_second]}))
    assert runner.statuses()[0].state is RuleState.RUNNING
    actions.block_speed.set()
    await runner.wait_idle()


async def test_close_cancels_and_rejects_future_work() -> None:
    actions = _Actions()
    actions.block_speed = asyncio.Event()
    runner = AutomationRunner(_functions(actions))
    document = _parser(actions).parse(_document(_speed(10)))
    await runner.replace(document)
    await runner.trigger(TRIGGER)
    await asyncio.wait_for(actions.speed_started.wait(), timeout=1)

    await runner.close()
    assert runner.statuses()[0].state is RuleState.IDLE
    with pytest.raises(RuntimeError, match="runner is closed"):
        await runner.trigger(TRIGGER)
    with pytest.raises(RuntimeError, match="runner is closed"):
        await runner.replace(document)
    await runner.close()


async def test_cancelled_close_still_awaits_rule_cancellation_cleanup() -> None:
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()

    async def set_speed(
        context: FunctionContext,
        config: SetTrainSpeedConfig,
    ) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_started.set()
            await release_cleanup.wait()

    functions = FunctionRegistry([SetTrainSpeedFunction(set_speed)])
    parser = AutomationParser(functions)
    runner = AutomationRunner(functions)
    await runner.replace(parser.parse(_document(_speed(10))))
    await runner.trigger(TRIGGER)
    await asyncio.sleep(0)

    closing = asyncio.create_task(runner.close())
    await asyncio.wait_for(cleanup_started.wait(), timeout=1)
    closing.cancel()
    await asyncio.sleep(0)
    assert not closing.done()

    release_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await closing
    assert runner.statuses()[0].state is RuleState.IDLE
    with pytest.raises(RuntimeError, match="runner is closed"):
        await runner.trigger(TRIGGER)


async def test_rebinding_function_changes_future_dispatch() -> None:
    first_actions = _Actions()
    second_actions = _Actions()
    functions = _functions(first_actions)
    parser = AutomationParser(functions)
    runner = AutomationRunner(functions)
    document = parser.parse(_document(_speed(10)))
    await runner.replace(document)
    await _run_once(runner)

    functions.replace(SetTrainSpeedFunction(second_actions.set_speed))
    await runner.replace(parser.parse(_document(_speed(10))))
    await _run_once(runner)

    assert [call[-1] for call in first_actions.calls] == [10]
    assert [call[-1] for call in second_actions.calls] == [10]


class _InvalidDecisionFunction(NodeFunction):
    type = "invalid_decision"
    children_policy = ChildrenPolicy.FORBIDDEN
    fields = frozenset()

    def parse(self, value, path: str) -> object:
        return None

    async def execute(self, context: FunctionContext, node: Node):
        return "enter_children"


async def test_invalid_plugin_decision_is_a_structured_node_failure() -> None:
    functions = FunctionRegistry([_InvalidDecisionFunction()])
    parser = AutomationParser(functions)
    runner = AutomationRunner(functions)
    await runner.replace(parser.parse(_document({
        "type": "invalid_decision",
        "children": [],
    })))

    await _run_once(runner)

    status = runner.statuses()[0]
    assert status.failure is not None
    assert status.failure.node_type == "invalid_decision"
    assert status.failure.node_path == (0,)
    assert "returned invalid decision" in status.failure.message


class _InvalidSelectionFunction(NodeFunction):
    type = "invalid_selection"
    children_policy = ChildrenPolicy.REQUIRED
    fields = frozenset({"index"})

    def parse(self, value, path: str) -> object:
        return value["index"]

    async def execute(self, context: FunctionContext, node: Node) -> ChildSelection:
        return ChildSelection(index=node.config)


@pytest.mark.parametrize("index", [True, -1, 1, "0"])
async def test_invalid_child_selection_is_parent_node_failure(index: object) -> None:
    actions = _Actions()
    functions = FunctionRegistry([
        _InvalidSelectionFunction(),
        SetTrainSpeedFunction(actions.set_speed),
    ])
    parser = AutomationParser(functions)
    runner = AutomationRunner(functions)
    await runner.replace(parser.parse(_document({
        "type": "invalid_selection",
        "index": index,
        "children": [_speed(10)],
    })))

    await _run_once(runner)

    status = runner.statuses()[0]
    assert status.failure is not None
    assert status.failure.node_type == "invalid_selection"
    assert status.failure.node_path == (0,)
    assert "selected invalid child index" in status.failure.message
    assert actions.calls == []


async def test_invalid_builtin_config_is_a_structured_node_failure() -> None:
    actions = _Actions()
    functions = _functions(actions)
    parser = AutomationParser(functions)
    document = parser.parse(_document(_speed(10)))
    rule = document.rules[0]
    invalid_node = replace(rule.children[0], config=None)
    document = replace(document, rules=(replace(rule, children=(invalid_node,)),))
    runner = AutomationRunner(functions)
    await runner.replace(document)

    await _run_once(runner)

    status = runner.statuses()[0]
    assert status.failure is not None
    assert status.failure.node_type == "set_train_speed"
    assert status.failure.message == (
        "set_train_speed node requires SetTrainSpeedConfig, got NoneType"
    )


async def test_replace_rejects_document_when_function_was_unplugged() -> None:
    actions = _Actions()
    functions = _functions(actions)
    parser = AutomationParser(functions)
    document = parser.parse(_document(_speed(10)))
    functions.unregister("set_train_speed")
    runner = AutomationRunner(functions)

    with pytest.raises(ValueError, match="functions are not registered: set_train_speed"):
        await runner.replace(document)
