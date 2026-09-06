from __future__ import annotations

import json
from pathlib import Path

import pytest

from train.config import (
    ConfigError,
    default_arduinos_path,
    default_automation_path,
    default_trains_path,
    load_runtime_config,
    normalized_arduinos_document,
    validate_arduino_upload_config,
)


def _write_config(root: Path) -> None:
    (root / "backend.json").write_text(json.dumps({
        "api": {"host": "127.0.0.1", "port": 8080, "url": "http://host:8080/"},
        "arduino_server": {"host": "127.0.0.1", "port": 9000},
    }))
    (root / "trains.json").write_text(json.dumps({
        "trains": [
            {
                "id": "train_1",
                "ble_address": "AA:BB",
                "tag_ids": ["04:ab", "04:cd"],
            },
            {"id": "train_2", "ble_address": "CC:DD", "tag_ids": []},
        ]
    }))
    (root / "arduinos.json").write_text(json.dumps({
        "devices": {
            "arduino_1": _device("hub_1", 4, 9),
            "arduino_2": _device("hub_2", 5, 10),
        }
    }))


def _device(hub_id: str, reader_pin: int, switch_pin: int) -> dict:
    return {
        "hub_id": hub_id,
        "port": "/dev/test",
        "fqbn": "vendor:board:model",
        "backend_host": "127.0.0.1",
        "baudrate": 9600,
        "backend_port": 9000,
        "servo_settle_ms": 500,
        "reconnect_ms": 2000,
        "switches": [
            {"id": "S1", "pin": switch_pin, "straight": 58, "diverge": 100}
        ],
        "readers": [
            {
                "id": "D1",
                "ss_pin": reader_pin,
                "read_timeout_ms": 250,
                "removal_delay_ms": 750,
            }
        ],
    }


def test_load_runtime_config_from_explicit_workspace(tmp_path: Path) -> None:
    _write_config(tmp_path)

    config = load_runtime_config(tmp_path)

    assert config.backend.api_url == "http://host:8080"
    assert config.train_map == {"AA:BB": "train_1", "CC:DD": "train_2"}
    assert [train.lego_hub_id for train in config.trains] == [
        "train_1",
        "train_2",
    ]
    assert config.trains[0].tag_ids == ("04:AB", "04:CD")
    assert config.trains[1].tag_ids == ()
    assert config.train_tag_map == {
        "04:AB": "train_1",
        "04:CD": "train_1",
    }
    assert [device.hub_id for device in config.arduinos] == ["hub_1", "hub_2"]
    assert config.arduino_hubs["hub_1"] == {
        "device_id": "arduino_1",
        "switches": {
            "S1": {"pin": 9, "straight": 58, "diverge": 100}
        },
        "detectors": ("D1",),
        "servo_settle_ms": 500,
        "readers": {
            "D1": {
                "ss_pin": 4,
                "read_timeout_ms": 250,
                "removal_delay_ms": 750,
            }
        },
    }


def test_automation_path_can_be_separate_from_immutable_runtime_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "persistent" / "automations.json"
    monkeypatch.setenv("TRAIN_AUTOMATIONS_PATH", str(path))

    assert default_automation_path() == path


def test_trains_path_can_be_separate_from_immutable_runtime_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "persistent" / "trains.json"
    monkeypatch.setenv("TRAIN_TRAINS_PATH", str(path))

    assert default_trains_path() == path


def test_arduinos_path_can_be_separate_from_immutable_runtime_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "persistent" / "arduinos.json"
    monkeypatch.setenv("TRAIN_ARDUINOS_PATH", str(path))

    assert default_arduinos_path() == path


def test_normalized_arduinos_document_includes_all_non_secret_fields(
    tmp_path: Path,
) -> None:
    _write_config(tmp_path)
    source = json.loads((tmp_path / "arduinos.json").read_text())

    normalized = normalized_arduinos_document(source)

    first = normalized["devices"]["arduino_1"]
    assert first == {
        "port": "/dev/test",
        "fqbn": "vendor:board:model",
        "baudrate": 9600,
        "hub_id": "hub_1",
        "backend_host": "127.0.0.1",
        "backend_port": 9000,
        "servo_settle_ms": 500,
        "reconnect_ms": 2000,
        "event_logger_enabled": False,
        "switches": [
            {"id": "S1", "pin": 9, "straight": 58, "diverge": 100}
        ],
        "readers": [
            {
                "id": "D1",
                "ss_pin": 4,
                "read_timeout_ms": 250,
                "removal_delay_ms": 750,
            }
        ],
    }
    assert "wifi_ssid" not in json.dumps(normalized)


def test_normalized_arduinos_document_rejects_unknown_fields(
    tmp_path: Path,
) -> None:
    _write_config(tmp_path)
    source = json.loads((tmp_path / "arduinos.json").read_text())
    source["devices"]["arduino_1"]["secret"] = "nope"

    with pytest.raises(ConfigError, match="unsupported field"):
        normalized_arduinos_document(source)


def test_legacy_hello_option_is_rejected(tmp_path: Path) -> None:
    _write_config(tmp_path)
    source = json.loads((tmp_path / "arduinos.json").read_text())
    source["devices"]["arduino_1"]["allow_legacy_hello"] = True

    with pytest.raises(ConfigError, match="allow_legacy_hello"):
        normalized_arduinos_document(source)


def test_default_runtime_load_uses_persistent_trains_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = tmp_path / "release"
    release.mkdir()
    _write_config(release)
    persistent = tmp_path / "persistent" / "trains.json"
    persistent.parent.mkdir()
    persistent.write_text(json.dumps({
        "trains": [
            {"id": "persisted", "ble_address": "11:22", "tag_ids": []}
        ]
    }))
    monkeypatch.setenv("TRAIN_DATA_DIR", str(release))
    monkeypatch.setenv("TRAIN_TRAINS_PATH", str(persistent))

    config = load_runtime_config()

    assert [train.train_id for train in config.trains] == ["persisted"]


@pytest.mark.parametrize("field", ["id", "ble_address"])
def test_duplicate_train_identity_is_rejected(tmp_path: Path, field: str) -> None:
    _write_config(tmp_path)
    trains = json.loads((tmp_path / "trains.json").read_text())
    trains["trains"][1][field] = trains["trains"][0][field]
    (tmp_path / "trains.json").write_text(json.dumps(trains))

    with pytest.raises(ConfigError, match="duplicate value"):
        load_runtime_config(tmp_path)


def test_duplicate_tag_id_across_trains_is_rejected(tmp_path: Path) -> None:
    _write_config(tmp_path)
    trains = json.loads((tmp_path / "trains.json").read_text())
    trains["trains"][1]["tag_ids"] = [" 04:CD "]
    (tmp_path / "trains.json").write_text(json.dumps(trains))

    with pytest.raises(ConfigError, match="duplicate value"):
        load_runtime_config(tmp_path)


def test_duplicate_tag_id_within_train_is_rejected(tmp_path: Path) -> None:
    _write_config(tmp_path)
    trains = json.loads((tmp_path / "trains.json").read_text())
    trains["trains"][0]["tag_ids"] = ["04:AB", "04:ab"]
    (tmp_path / "trains.json").write_text(json.dumps(trains))

    with pytest.raises(ConfigError, match="duplicate value"):
        load_runtime_config(tmp_path)


@pytest.mark.parametrize(
    ("target", "field"),
    [("root", "unexpected"), ("train", "color")],
)
def test_unsupported_train_fields_are_rejected(
    tmp_path: Path, target: str, field: str
) -> None:
    _write_config(tmp_path)
    trains = json.loads((tmp_path / "trains.json").read_text())
    if target == "root":
        trains[field] = True
    else:
        trains["trains"][0][field] = "red"
    (tmp_path / "trains.json").write_text(json.dumps(trains))

    with pytest.raises(ConfigError, match=rf"unsupported field\(s\): {field}"):
        load_runtime_config(tmp_path)


def test_duplicate_legacy_tag_id_keeps_legacy_error_path(tmp_path: Path) -> None:
    _write_config(tmp_path)
    trains = json.loads((tmp_path / "trains.json").read_text())
    for train in trains["trains"]:
        train.pop("tag_ids")
    trains["trains"][0]["tag_id"] = "04:AB"
    trains["trains"][1]["tag_id"] = "04:ab"
    (tmp_path / "trains.json").write_text(json.dumps(trains))

    with pytest.raises(
        ConfigError,
        match=r"trains\[1\]\.tag_id: duplicate value",
    ):
        load_runtime_config(tmp_path)


def test_missing_workspace_points_to_initializer(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="tools/data init"):
        load_runtime_config(tmp_path)


def test_explicit_lego_hub_id_is_loaded(tmp_path: Path) -> None:
    _write_config(tmp_path)
    trains = json.loads((tmp_path / "trains.json").read_text())
    trains["trains"][0]["lego_hub_id"] = "hub_red"
    (tmp_path / "trains.json").write_text(json.dumps(trains))

    config = load_runtime_config(tmp_path)

    assert config.trains[0].lego_hub_id == "hub_red"


def test_duplicate_lego_hub_identity_is_rejected(tmp_path: Path) -> None:
    _write_config(tmp_path)
    trains = json.loads((tmp_path / "trains.json").read_text())
    trains["trains"][0]["lego_hub_id"] = "shared_hub"
    trains["trains"][1]["lego_hub_id"] = "shared_hub"
    (tmp_path / "trains.json").write_text(json.dumps(trains))

    with pytest.raises(ConfigError, match="duplicate value"):
        load_runtime_config(tmp_path)


def test_duplicate_hub_identity_is_rejected(tmp_path: Path) -> None:
    _write_config(tmp_path)
    devices = json.loads((tmp_path / "arduinos.json").read_text())
    devices["devices"]["arduino_2"]["hub_id"] = "hub_1"
    (tmp_path / "arduinos.json").write_text(json.dumps(devices))

    with pytest.raises(ConfigError, match="duplicate value"):
        load_runtime_config(tmp_path)


def test_duplicate_hardware_pin_is_rejected(tmp_path: Path) -> None:
    _write_config(tmp_path)
    devices = json.loads((tmp_path / "arduinos.json").read_text())
    devices["devices"]["arduino_1"]["readers"][0]["ss_pin"] = 9
    (tmp_path / "arduinos.json").write_text(json.dumps(devices))

    with pytest.raises(ConfigError, match="duplicates pin"):
        validate_arduino_upload_config(tmp_path)


@pytest.mark.parametrize("tag_ids", [None, True, 123, "04:AB"])
def test_train_tag_ids_must_be_a_list(tmp_path: Path, tag_ids: object) -> None:
    _write_config(tmp_path)
    trains = json.loads((tmp_path / "trains.json").read_text())
    trains["trains"][0]["tag_ids"] = tag_ids
    (tmp_path / "trains.json").write_text(json.dumps(trains))

    with pytest.raises(ConfigError, match="tag_ids must be a list"):
        load_runtime_config(tmp_path)


@pytest.mark.parametrize("tag_id", [None, True, 123, "", "   "])
def test_train_tag_ids_must_contain_non_empty_strings(
    tmp_path: Path, tag_id: object
) -> None:
    _write_config(tmp_path)
    trains = json.loads((tmp_path / "trains.json").read_text())
    trains["trains"][0]["tag_ids"] = [tag_id]
    (tmp_path / "trains.json").write_text(json.dumps(trains))

    with pytest.raises(
        ConfigError,
        match=r"tag_ids\[0\] must be a non-empty string",
    ):
        load_runtime_config(tmp_path)


def test_legacy_train_tag_id_remains_supported(tmp_path: Path) -> None:
    _write_config(tmp_path)
    trains = json.loads((tmp_path / "trains.json").read_text())
    trains["trains"][0].pop("tag_ids")
    trains["trains"][0]["tag_id"] = " 04:ef "
    trains["trains"][1].pop("tag_ids")
    trains["trains"][1]["tag_id"] = ""
    (tmp_path / "trains.json").write_text(json.dumps(trains))

    config = load_runtime_config(tmp_path)

    assert config.trains[0].tag_ids == ("04:EF",)
    assert config.trains[1].tag_ids == ()


@pytest.mark.parametrize("tag_id", [None, True, 123])
def test_legacy_train_tag_id_must_be_a_string(
    tmp_path: Path, tag_id: object
) -> None:
    _write_config(tmp_path)
    trains = json.loads((tmp_path / "trains.json").read_text())
    trains["trains"][0].pop("tag_ids")
    trains["trains"][0]["tag_id"] = tag_id
    (tmp_path / "trains.json").write_text(json.dumps(trains))

    with pytest.raises(ConfigError, match="tag_id must be a string"):
        load_runtime_config(tmp_path)


def test_train_must_not_mix_legacy_and_plural_tag_fields(tmp_path: Path) -> None:
    _write_config(tmp_path)
    trains = json.loads((tmp_path / "trains.json").read_text())
    trains["trains"][0]["tag_id"] = "04:EF"
    (tmp_path / "trains.json").write_text(json.dumps(trains))

    with pytest.raises(
        ConfigError,
        match="must not define both tag_id and tag_ids",
    ):
        load_runtime_config(tmp_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("backend_port", 65536),
        ("baudrate", 0x100000000),
        ("servo_settle_ms", 0x100000000),
        ("reconnect_ms", 0x100000000),
    ],
)
def test_firmware_integer_limits_are_enforced(
    tmp_path: Path, field: str, value: int
) -> None:
    _write_config(tmp_path)
    devices = json.loads((tmp_path / "arduinos.json").read_text())
    devices["devices"]["arduino_1"][field] = value
    (tmp_path / "arduinos.json").write_text(json.dumps(devices))

    with pytest.raises(ConfigError, match=field):
        validate_arduino_upload_config(tmp_path)


@pytest.mark.parametrize(("value", "valid"), [(1000, True), (1001, False)])
def test_reader_timeout_must_stay_below_heartbeat_budget(
    tmp_path: Path, value: int, valid: bool
) -> None:
    _write_config(tmp_path)
    devices = json.loads((tmp_path / "arduinos.json").read_text())
    devices["devices"]["arduino_1"]["readers"][0]["read_timeout_ms"] = value
    (tmp_path / "arduinos.json").write_text(json.dumps(devices))

    if valid:
        validate_arduino_upload_config(tmp_path)
    else:
        with pytest.raises(ConfigError, match="read_timeout_ms"):
            validate_arduino_upload_config(tmp_path)


def test_event_logger_flag_must_be_boolean(tmp_path: Path) -> None:
    _write_config(tmp_path)
    devices = json.loads((tmp_path / "arduinos.json").read_text())
    devices["devices"]["arduino_1"]["event_logger_enabled"] = "yes"
    (tmp_path / "arduinos.json").write_text(json.dumps(devices))

    with pytest.raises(ConfigError, match="event_logger_enabled"):
        validate_arduino_upload_config(tmp_path)


def test_upload_only_fields_do_not_block_backend_config(tmp_path: Path) -> None:
    _write_config(tmp_path)
    devices = json.loads((tmp_path / "arduinos.json").read_text())
    devices["devices"]["arduino_1"]["port"] = ""
    (tmp_path / "arduinos.json").write_text(json.dumps(devices))

    load_runtime_config(tmp_path)
    with pytest.raises(ConfigError, match="port"):
        validate_arduino_upload_config(tmp_path)
