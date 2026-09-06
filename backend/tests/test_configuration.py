from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from train.configuration import (
    ConfigurationConflict,
    ConfigurationDocument,
    ConfigurationError,
    ConfigurationStore,
)


def _write_trains(path: Path) -> None:
    path.write_text(json.dumps({
        "trains": [
            {
                "id": "express",
                "ble_address": "AA:BB",
                "tag_ids": ["04:ab"],
            }
        ]
    }))
    os.utime(path, (1000, 1000))


def test_snapshot_is_versioned_and_normalized(tmp_path: Path) -> None:
    path = tmp_path / "trains.json"
    _write_trains(path)
    store = ConfigurationStore.for_trains(path)

    assert store.snapshot() == {
        "version": 1,
        "documents": {
            "trains": {
                "modified_at": 1000.0,
                "restart_required": True,
                "value": {
                    "trains": [
                        {
                            "id": "express",
                            "lego_hub_id": "express",
                            "ble_address": "AA:BB",
                            "tag_ids": ["04:AB"],
                        }
                    ]
                },
            }
        },
    }


def test_document_value_is_a_defensive_copy(tmp_path: Path) -> None:
    path = tmp_path / "trains.json"
    _write_trains(path)
    store = ConfigurationStore.for_trains(path)

    value = store.document_value("trains")
    value["trains"] = []

    assert len(store.document_value("trains")["trains"]) == 1


async def test_replace_validates_and_atomically_persists(tmp_path: Path) -> None:
    path = tmp_path / "trains.json"
    _write_trains(path)
    store = ConfigurationStore.for_trains(path)
    replacement = {
        "version": 1,
        "documents": {
            "trains": {
                "base_modified_at": 1000,
                "modified_at": 2000,
                "value": {
                    "trains": [
                        {
                            "id": " local ",
                            "lego_hub_id": " hub ",
                            "ble_address": " CC:DD ",
                            "tag_ids": [" 04:ef "],
                        }
                    ]
                },
            }
        },
    }

    snapshot = await store.replace_json(json.dumps(replacement))

    assert snapshot["documents"]["trains"]["modified_at"] == 2000
    assert json.loads(path.read_text()) == {
        "trains": [
            {
                "id": "local",
                "lego_hub_id": "hub",
                "ble_address": "CC:DD",
                "tag_ids": ["04:EF"],
            }
        ]
    }
    assert list(tmp_path.glob(".trains.json.*.tmp")) == []


async def test_replace_uses_server_timestamp_when_client_omits_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "trains.json"
    _write_trains(path)
    store = ConfigurationStore.for_trains(path)
    monkeypatch.setattr("train.configuration.time.time", lambda: 1500.0)

    snapshot = await store.replace_json(json.dumps({
        "version": 1,
        "documents": {
            "trains": {
                "base_modified_at": 1000,
                "value": {
                    "trains": [
                        {"id": "other", "ble_address": "CC:DD", "tag_ids": []}
                    ]
                },
            }
        },
    }))

    assert snapshot["documents"]["trains"]["modified_at"] == 1500


async def test_replace_rejects_stale_different_document(tmp_path: Path) -> None:
    path = tmp_path / "trains.json"
    _write_trains(path)
    store = ConfigurationStore.for_trains(path)

    with pytest.raises(ConfigurationConflict, match="must be newer"):
        await store.replace_json(json.dumps({
            "version": 1,
            "documents": {
                "trains": {
                    "base_modified_at": 1000,
                    "modified_at": 999,
                    "value": {
                        "trains": [
                            {"id": "other", "ble_address": "CC:DD", "tag_ids": []}
                        ]
                    },
                }
            },
        }))

    assert json.loads(path.read_text())["trains"][0]["id"] == "express"


async def test_replace_rejects_editor_based_on_an_older_snapshot(
    tmp_path: Path,
) -> None:
    path = tmp_path / "trains.json"
    _write_trains(path)
    store = ConfigurationStore.for_trains(path)
    os.utime(path, (1500, 1500))

    with pytest.raises(ConfigurationConflict, match="does not match"):
        await store.replace_json(json.dumps({
            "version": 1,
            "documents": {
                "trains": {
                    "base_modified_at": 1000,
                    "modified_at": 2000,
                    "value": {
                        "trains": [
                            {"id": "other", "ble_address": "CC:DD", "tag_ids": []}
                        ]
                    },
                }
            },
        }))


async def test_replace_rejects_invalid_train_document(tmp_path: Path) -> None:
    path = tmp_path / "trains.json"
    _write_trains(path)
    store = ConfigurationStore.for_trains(path)

    with pytest.raises(ConfigurationError, match="non-empty list"):
        await store.replace_json(json.dumps({
            "version": 1,
            "documents": {
                "trains": {
                    "base_modified_at": 1000,
                    "modified_at": 2000,
                    "value": {"trains": []},
                }
            },
        }))


async def test_two_document_store_validates_complete_candidate_before_write(
    tmp_path: Path,
) -> None:
    trains = tmp_path / "trains.json"
    arduinos = tmp_path / "arduinos.json"
    trains.write_text('{"trains": [{"id": "old"}]}')
    arduinos.write_text('{"devices": {"board": {"hub": "old"}}}')
    os.utime(trains, (1000, 1000))
    os.utime(arduinos, (1000, 1000))
    candidates: list[dict[str, dict[str, object]]] = []

    def normalize(value: dict[str, object]) -> dict[str, object]:
        return value

    def validate(value) -> None:
        candidates.append(dict(value))
        if value["arduinos"]["devices"] == {}:
            raise ValueError("at least one Arduino is required")

    store = ConfigurationStore(
        {
            "trains": ConfigurationDocument(trains, normalize),
            "arduinos": ConfigurationDocument(arduinos, normalize),
        },
        validate=validate,
    )

    snapshot = await store.replace_json(json.dumps({
        "version": 1,
        "documents": {
            "arduinos": {
                "base_modified_at": 1000,
                "value": {"devices": {"board": {"hub": "new"}}},
            }
        },
    }))

    assert snapshot["documents"]["trains"]["value"] == {
        "trains": [{"id": "old"}]
    }
    assert candidates[-1]["arduinos"] == {
        "devices": {"board": {"hub": "new"}}
    }

    with pytest.raises(ConfigurationError, match="at least one Arduino"):
        await store.replace_json(json.dumps({
            "version": 1,
            "documents": {
                "arduinos": {
                    "base_modified_at": snapshot["documents"]["arduinos"]["modified_at"],
                    "value": {"devices": {}},
                }
            },
        }))
    assert json.loads(arduinos.read_text()) == {
        "devices": {"board": {"hub": "new"}}
    }
