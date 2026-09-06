from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from automation_tree import AutomationParseError, RuleState
from train.config import BackendConfig, RuntimeConfig, TrainConfig
from train.core.event_bus import EventBus
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
from train.modules import automation as automation_module
from train.modules.automation import AutomationModule


def _document(
    *children: dict[str, object],
    version: int = 3,
) -> dict[str, object]:
    return {
        "version": version,
        "rules": [{
            "id": "station",
            "enabled": True,
            "root": {
                "type": "train_detected",
                "hub_id": "yard",
                "detector_id": "D1",
                "train_id": "express",
                "children": list(children),
            },
        }],
    }


def _speed(speed: int) -> dict[str, object]:
    return {"type": "set_train_speed", "speed": speed, "children": []}


def _wait(seconds: float, *children: dict[str, object]) -> dict[str, object]:
    return {"type": "wait", "seconds": seconds, "children": list(children)}


def _switch(position: str) -> dict[str, object]:
    return {
        "type": "set_switch",
        "hub_id": "yard",
        "switch_id": "S1",
        "position": position,
        "children": [],
    }


@pytest.fixture
def bus() -> EventBus:
    return EventBus(SystemState.from_topology(
        train_hubs={"express": "express_hub", "untagged": "untagged_hub"},
        arduino_hubs={
            "yard": {"switches": {"S1": {}}, "detectors": ("D1",)}
        },
    ))


def _write(path: Path, document: dict[str, object]) -> None:
    path.write_text(json.dumps(document))


async def _acknowledge_commands(
    bus: EventBus,
) -> tuple[list[SetTrainSpeed], list[SetSwitchPosition]]:
    speeds: list[SetTrainSpeed] = []
    switches: list[SetSwitchPosition] = []

    async def set_speed(command: SetTrainSpeed) -> None:
        speeds.append(command)
        await bus.publish(TrainSpeedChanged(
            train_name=command.train_name,
            speed=command.speed,
            success=True,
            request_id=command.request_id,
        ))

    async def set_switch(command: SetSwitchPosition) -> None:
        switches.append(command)
        await bus.publish(SwitchPositionChanged(
            hub_name=command.hub_name,
            switch_name=command.switch_name,
            angle=90,
            ok=True,
            request_id=command.request_id,
        ))

    bus.subscribe(SetTrainSpeed, set_speed)
    bus.subscribe(SetSwitchPosition, set_switch)
    return speeds, switches


async def test_module_runs_matching_tree_with_acknowledged_commands(
    bus: EventBus, tmp_path: Path
) -> None:
    path = tmp_path / "automations.json"
    _write(path, _document(_switch("diverge"), _speed(45)))
    speeds, switches = await _acknowledge_commands(bus)
    module = AutomationModule(bus, path=path, tagged_trains={"express"})
    await module.start()

    try:
        await bus.publish(TagDetected(
            hub_name="yard", detector_name="D1", train_id="express"
        ))
        await module._runner.wait_idle()

        assert [(item.hub_name, item.switch_name, item.target) for item in switches] == [
            ("yard", "S1", "diverge")
        ]
        assert [(item.train_name, item.speed) for item in speeds] == [
            ("express", 45)
        ]
        assert module.snapshot()["eligible_train_ids"] == ["express"]
        assert module.snapshot()["statuses"][0]["state"] is RuleState.IDLE
    finally:
        await module.stop()


async def test_module_dispatches_flip_switch_target(
    bus: EventBus, tmp_path: Path
) -> None:
    path = tmp_path / "automations.json"
    _write(path, _document(_switch("flip")))
    _, switches = await _acknowledge_commands(bus)
    module = AutomationModule(bus, path=path, tagged_trains={"express"})
    await module.start()

    try:
        await bus.publish(TagDetected(
            hub_name="yard", detector_name="D1", train_id="express"
        ))
        await module._runner.wait_idle()

        assert [item.target for item in switches] == ["flip"]
    finally:
        await module.stop()


async def test_module_executes_count_branch_and_migrates_version_2(
    bus: EventBus, tmp_path: Path
) -> None:
    branch = {
        "type": "if_count",
        "count": 2,
        "children": [
            {"type": "branch", "when": "match", "children": [_switch("diverge")]},
            {
                "type": "branch",
                "when": "otherwise",
                "children": [_switch("straight")],
            },
        ],
    }
    document = _document(branch, version=2)
    path = tmp_path / "automations.json"
    _write(path, document)
    _, switches = await _acknowledge_commands(bus)
    module = AutomationModule(bus, path=path, tagged_trains={"express"})
    await module.start()

    try:
        for _ in range(2):
            await bus.publish(TagDetected(
                hub_name="yard", detector_name="D1", train_id="express"
            ))
            await module._runner.wait_idle()

        assert [item.target for item in switches] == ["straight", "diverge"]
        expected = {**document, "version": 3}
        assert module.snapshot()["document"] == expected
        assert json.loads(path.read_text()) == expected
    finally:
        await module.stop()


async def test_replacement_cancels_old_tree_and_persists_new_document(
    bus: EventBus, tmp_path: Path
) -> None:
    path = tmp_path / "automations.json"
    _write(path, _document(_wait(10, _speed(10))))
    speeds, _ = await _acknowledge_commands(bus)
    module = AutomationModule(bus, path=path, tagged_trains={"express"})
    await module.start()

    try:
        await bus.publish(TagDetected(
            hub_name="yard", detector_name="D1", train_id="express"
        ))
        await asyncio.sleep(0)
        assert module.snapshot()["statuses"][0]["state"] is RuleState.WAITING

        replacement = _document(_speed(30))
        snapshot = await module.replace_json(json.dumps(replacement))
        assert snapshot["document"] == replacement
        assert json.loads(path.read_text()) == replacement

        await bus.publish(TagDetected(
            hub_name="yard", detector_name="D1", train_id="express"
        ))
        await module._runner.wait_idle()
        assert [command.speed for command in speeds] == [30]
    finally:
        await module.stop()


async def test_api_replacement_migrates_legacy_document_before_activation(
    bus: EventBus, tmp_path: Path
) -> None:
    path = tmp_path / "automations.json"
    original = _document(_speed(10))
    _write(path, original)
    module = AutomationModule(bus, path=path, tagged_trains={"express"})
    await module.start()

    try:
        legacy = _document(_speed(30), version=1)
        snapshot = await module.replace_json(json.dumps(legacy))
        expected = {**legacy, "version": 3}
        assert snapshot["document"] == expected
        assert json.loads(path.read_text()) == expected
        assert module._runner.document.version == 3
    finally:
        await module.stop()


async def test_post_rename_failure_restores_previous_document(
    bus: EventBus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "automations.json"
    original = _document(_speed(10))
    _write(path, original)
    module = AutomationModule(bus, path=path, tagged_trains={"express"})
    await module.start()
    replace_document = automation_module._replace_document
    calls = 0

    def fail_after_first_rename(staged: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        replace_document(staged, destination)
        if calls == 1:
            raise OSError("directory fsync failed")

    monkeypatch.setattr(
        automation_module,
        "_replace_document",
        fail_after_first_rename,
    )
    try:
        with pytest.raises(OSError, match="directory fsync failed"):
            await module.replace_json(json.dumps(_document(_speed(30))))
        assert json.loads(path.read_text()) == original
        assert module.snapshot()["document"] == original
        assert module.healthy
    finally:
        await module.stop()


async def test_unreconciled_persistence_closes_module_before_admission(
    bus: EventBus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "automations.json"
    original = _document(_speed(10))
    _write(path, original)
    speeds, _ = await _acknowledge_commands(bus)
    module = AutomationModule(bus, path=path, tagged_trains={"express"})
    await module.start()
    replace_document = automation_module._replace_document

    def fail_after_every_rename(staged: Path, destination: Path) -> None:
        replace_document(staged, destination)
        raise OSError("directory fsync failed")

    monkeypatch.setattr(
        automation_module,
        "_replace_document",
        fail_after_every_rename,
    )
    try:
        with pytest.raises(RuntimeError, match="could not be restored"):
            await module.replace_json(json.dumps(_document(_speed(30))))
        assert not module.healthy
        assert module.snapshot()["document"] == original
        with pytest.raises(RuntimeError, match="terminal"):
            await module.replace_json(json.dumps(_document(_speed(40))))
        await bus.publish(TagDetected(
            hub_name="yard", detector_name="D1", train_id="express"
        ))
        assert speeds == []
    finally:
        await module.stop()


async def test_activation_and_file_rollback_failure_keeps_candidate_inadmissible(
    bus: EventBus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "automations.json"
    original = _document(_speed(10))
    candidate = _document(_speed(30))
    _write(path, original)
    speeds, _ = await _acknowledge_commands(bus)
    module = AutomationModule(bus, path=path, tagged_trains={"express"})
    await module.start()
    runner_replace = module._runner.replace
    persist = automation_module._persist_with_rollback
    persistence_calls = 0

    async def fail_candidate_activation(document, **kwargs: object) -> None:
        if document.rules[0].children[0].config.speed == 30:
            raise RuntimeError("activation failed")
        await runner_replace(document, **kwargs)

    def fail_file_rollback(*args: object, **kwargs: object) -> None:
        nonlocal persistence_calls
        persistence_calls += 1
        if persistence_calls == 2:
            raise OSError("file rollback failed")
        persist(*args, **kwargs)

    monkeypatch.setattr(module._runner, "replace", fail_candidate_activation)
    monkeypatch.setattr(
        automation_module,
        "_persist_with_rollback",
        fail_file_rollback,
    )
    try:
        with pytest.raises(RuntimeError, match="could not be restored"):
            await module.replace_json(json.dumps(candidate))
        assert not module.healthy
        assert module.snapshot()["document"] == original
        assert module._runner.document.rules[0].children[0].config.speed == 10
        with pytest.raises(RuntimeError, match="terminal"):
            await module.replace_json(json.dumps(_document(_speed(40))))
        await bus.publish(TagDetected(
            hub_name="yard", detector_name="D1", train_id="express"
        ))
        assert speeds == []
    finally:
        await module.stop()


async def test_startup_activation_failure_restores_legacy_file_and_closes_runner(
    bus: EventBus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "automations.json"
    legacy = _document(_speed(10), version=1)
    _write(path, legacy)
    module = AutomationModule(bus, path=path, tagged_trains={"express"})

    async def fail_activation(*args: object, **kwargs: object) -> None:
        raise RuntimeError("activation failed")

    monkeypatch.setattr(module._runner, "replace", fail_activation)
    with pytest.raises(RuntimeError, match="activation failed"):
        await module.start()

    assert json.loads(path.read_text()) == legacy
    assert not module.healthy
    with pytest.raises(RuntimeError, match="closed"):
        await module._runner.trigger(automation_module.Trigger("yard", "D1", "express"))


async def test_reapplying_same_document_cancels_its_active_execution(
    bus: EventBus, tmp_path: Path
) -> None:
    document = _document(_wait(10, _speed(10)))
    path = tmp_path / "automations.json"
    _write(path, document)
    speeds, _ = await _acknowledge_commands(bus)
    module = AutomationModule(bus, path=path, tagged_trains={"express"})
    await module.start()

    try:
        await bus.publish(TagDetected(
            hub_name="yard", detector_name="D1", train_id="express"
        ))
        await asyncio.sleep(0)
        assert module.snapshot()["statuses"][0]["state"] is RuleState.WAITING

        await module.replace_json(json.dumps(document))
        assert module.snapshot()["statuses"][0]["state"] is RuleState.IDLE
        assert speeds == []
    finally:
        await module.stop()


async def test_replacement_keeps_old_document_visible_until_cancellation_finishes(
    bus: EventBus, tmp_path: Path
) -> None:
    path = tmp_path / "automations.json"
    original = _document(_wait(10, _speed(10)))
    replacement = _document(_speed(30))
    _write(path, original)
    module = AutomationModule(bus, path=path, tagged_trains={"express"})
    cancellation_started = asyncio.Event()
    finish_cancellation = asyncio.Event()

    async def blocking_sleep(seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
        finally:
            cancellation_started.set()
            await finish_cancellation.wait()

    module._runner._sleep = blocking_sleep
    await module.start()

    try:
        await bus.publish(TagDetected(
            hub_name="yard", detector_name="D1", train_id="express"
        ))
        await asyncio.sleep(0)
        update = asyncio.create_task(module.replace_json(json.dumps(replacement)))
        await cancellation_started.wait()

        assert module.snapshot()["document"] == original
        assert not update.done()

        finish_cancellation.set()
        snapshot = await update
        assert snapshot["document"] == replacement
    finally:
        finish_cancellation.set()
        await module.stop()


async def test_detection_during_replacement_is_dropped_instead_of_replayed(
    bus: EventBus, tmp_path: Path
) -> None:
    path = tmp_path / "automations.json"
    original = _document(_wait(10, _speed(10)))
    replacement = _document(_speed(30))
    _write(path, original)
    speeds, _ = await _acknowledge_commands(bus)
    module = AutomationModule(bus, path=path, tagged_trains={"express"})
    cancellation_started = asyncio.Event()
    finish_cancellation = asyncio.Event()

    async def blocking_sleep(seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
        finally:
            cancellation_started.set()
            await finish_cancellation.wait()

    module._runner._sleep = blocking_sleep
    await module.start()

    try:
        await bus.publish(TagDetected(
            hub_name="yard", detector_name="D1", train_id="express"
        ))
        await asyncio.sleep(0)
        update = asyncio.create_task(module.replace_json(json.dumps(replacement)))
        await cancellation_started.wait()

        await bus.publish(TagDetected(
            hub_name="yard", detector_name="D1", train_id="express"
        ))
        finish_cancellation.set()
        await update
        await module._runner.wait_idle()
        assert speeds == []

        await bus.publish(TagDetected(
            hub_name="yard", detector_name="D1", train_id="express"
        ))
        await module._runner.wait_idle()
        assert [command.speed for command in speeds] == [30]
    finally:
        finish_cancellation.set()
        await module.stop()


async def test_concurrent_replacements_return_their_own_committed_document(
    bus: EventBus, tmp_path: Path
) -> None:
    path = tmp_path / "automations.json"
    _write(path, _document(_speed(10)))
    module = AutomationModule(bus, path=path, tagged_trains={"express"})
    await module.start()
    first = _document(_speed(20))
    second = _document(_speed(30))

    try:
        first_result, second_result = await asyncio.gather(
            module.replace_json(json.dumps(first)),
            module.replace_json(json.dumps(second)),
        )
        assert first_result["document"] == first
        assert second_result["document"] == second
        assert json.loads(path.read_text()) == second
    finally:
        await module.stop()


async def test_stop_waits_for_an_accepted_replacement(
    bus: EventBus, tmp_path: Path
) -> None:
    path = tmp_path / "automations.json"
    original = _document(_wait(10, _speed(10)))
    replacement = _document(_speed(30))
    _write(path, original)
    module = AutomationModule(bus, path=path, tagged_trains={"express"})
    cancellation_started = asyncio.Event()
    finish_cancellation = asyncio.Event()

    async def blocking_sleep(seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
        finally:
            cancellation_started.set()
            await finish_cancellation.wait()

    module._runner._sleep = blocking_sleep
    await module.start()
    await bus.publish(TagDetected(
        hub_name="yard", detector_name="D1", train_id="express"
    ))
    await asyncio.sleep(0)
    update = asyncio.create_task(module.replace_json(json.dumps(replacement)))
    await cancellation_started.wait()
    stop = asyncio.create_task(module.stop())
    await asyncio.sleep(0)

    assert not stop.done()

    finish_cancellation.set()
    await update
    await stop
    assert json.loads(path.read_text()) == replacement


async def test_status_changes_notify_subscribers(
    bus: EventBus, tmp_path: Path
) -> None:
    path = tmp_path / "automations.json"
    _write(path, _document(_wait(0, _speed(20))))
    await _acknowledge_commands(bus)
    module = AutomationModule(bus, path=path, tagged_trains={"express"})
    states: list[RuleState] = []

    def changed() -> None:
        statuses = module.snapshot()["statuses"]
        if statuses:
            states.append(statuses[0]["state"])

    module.subscribe_changes(changed)
    await module.start()
    try:
        await bus.publish(TagDetected(
            hub_name="yard", detector_name="D1", train_id="express"
        ))
        await module._runner.wait_idle()
        assert RuleState.RUNNING in states
        assert RuleState.WAITING in states
        assert states[-1] is RuleState.IDLE
    finally:
        await module.stop()


async def test_halt_cancels_work_and_resume_accepts_new_detection(
    bus: EventBus, tmp_path: Path
) -> None:
    path = tmp_path / "automations.json"
    _write(path, _document(_speed(20)))
    speeds, _ = await _acknowledge_commands(bus)
    module = AutomationModule(bus, path=path, tagged_trains={"express"})
    await module.start()

    try:
        await bus.publish(AutomationHalt())
        await bus.publish(TagDetected(
            hub_name="yard", detector_name="D1", train_id="express"
        ))
        assert speeds == []
        assert module.snapshot()["paused"] is True

        await bus.publish(AutomationResume())
        await bus.publish(TagDetected(
            hub_name="yard", detector_name="D1", train_id="express"
        ))
        await module._runner.wait_idle()
        assert [command.speed for command in speeds] == [20]
    finally:
        await module.stop()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("train_id", "missing", "unknown train"),
        ("train_id", "untagged", "has no configured tag"),
        ("hub_id", "missing", "unknown Arduino hub"),
        ("detector_id", "missing", "unknown detector"),
    ],
)
async def test_start_rejects_unknown_topology_references(
    bus: EventBus,
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    document = _document(_speed(20))
    document["rules"][0]["root"][field] = value
    path = tmp_path / "automations.json"
    _write(path, document)
    module = AutomationModule(bus, path=path, tagged_trains={"express"})

    with pytest.raises(AutomationParseError, match=message):
        await module.start()


async def test_update_rejects_unknown_switch_without_changing_active_document(
    bus: EventBus, tmp_path: Path
) -> None:
    original = _document(_speed(20))
    path = tmp_path / "automations.json"
    _write(path, original)
    module = AutomationModule(bus, path=path, tagged_trains={"express"})
    await module.start()

    replacement = _document({
        "type": "set_switch",
        "hub_id": "yard",
        "switch_id": "missing",
        "position": "straight",
        "children": [],
    })
    try:
        with pytest.raises(AutomationParseError, match="unknown switch"):
            await module.replace_json(json.dumps(replacement))
        assert module.snapshot()["document"] == original
        assert json.loads(path.read_text()) == original
    finally:
        await module.stop()


def test_candidate_can_be_validated_against_persisted_restart_topology(
    bus: EventBus,
    tmp_path: Path,
) -> None:
    module = AutomationModule(
        bus,
        path=tmp_path / "automations.json",
        tagged_trains={"express"},
    )
    future_config = RuntimeConfig(
        backend=BackendConfig(
            "localhost",
            8080,
            "http://localhost:8080",
            "localhost",
            9000,
        ),
        trains=(TrainConfig("other", "other_hub", "AA:BB", ()),),
        arduinos=(),
    )

    with pytest.raises(AutomationParseError, match="unknown train: express"):
        module.validate_json_for_runtime_config(
            json.dumps(_document(_speed(20))),
            future_config,
        )


async def test_missing_automation_file_has_guided_error(
    bus: EventBus, tmp_path: Path
) -> None:
    module = AutomationModule(
        bus,
        path=tmp_path / "automations.json",
        tagged_trains={"express"},
    )

    with pytest.raises(AutomationParseError, match="tools/data init"):
        await module.start()
