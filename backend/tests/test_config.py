from __future__ import annotations

import json
from pathlib import Path

import pytest

from train.config import (
    ConfigError,
    load_automation,
    load_runtime_config,
    validate_arduino_upload_config,
)


def _write_config(root: Path) -> None:
    (root / "backend.json").write_text(json.dumps({
        "api": {"host": "127.0.0.1", "port": 8080, "url": "http://host:8080/"},
        "arduino_server": {"host": "127.0.0.1", "port": 9000},
    }))
    (root / "trains.json").write_text(json.dumps({
        "trains": [
            {"id": "train_1", "ble_address": "AA:BB", "tag_id": "04:ab"},
            {"id": "train_2", "ble_address": "CC:DD", "tag_id": ""},
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
    assert config.train_tag_map == {"04:AB": "train_1"}
    assert [device.hub_id for device in config.arduinos] == ["hub_1", "hub_2"]
    assert config.arduino_hubs["hub_1"] == {
        "switches": {"S1": {"straight": 58, "diverge": 100}},
        "detectors": ("D1",),
    }


@pytest.mark.parametrize("field", ["id", "ble_address", "tag_id"])
def test_duplicate_train_identity_is_rejected(tmp_path: Path, field: str) -> None:
    _write_config(tmp_path)
    trains = json.loads((tmp_path / "trains.json").read_text())
    trains["trains"][1][field] = trains["trains"][0][field]
    (tmp_path / "trains.json").write_text(json.dumps(trains))

    with pytest.raises(ConfigError, match="duplicate value"):
        load_runtime_config(tmp_path)


def test_missing_workspace_points_to_initializer(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="tools/data init"):
        load_runtime_config(tmp_path)


def test_load_automation_entry_point(tmp_path: Path) -> None:
    (tmp_path / "automation.py").write_text(
        "def configure(ctx):\n    pass\n\nasync def run(ctx):\n    return ctx\n"
    )

    program = load_automation(tmp_path)

    assert program.configure.__name__ == "configure"
    assert program.run.__name__ == "run"


def test_automation_requires_run_function(tmp_path: Path) -> None:
    (tmp_path / "automation.py").write_text("def configure(ctx):\n    pass\n")

    with pytest.raises(ConfigError, match="must export"):
        load_automation(tmp_path)


def test_automation_requires_synchronous_configuration(tmp_path: Path) -> None:
    (tmp_path / "automation.py").write_text(
        "async def configure(ctx):\n    pass\n\nasync def run(ctx):\n    pass\n"
    )

    with pytest.raises(ConfigError, match="synchronous"):
        load_automation(tmp_path)


@pytest.mark.parametrize(
    "source",
    [
        "def configure():\n    pass\n\nasync def run(ctx):\n    pass\n",
        "def configure(ctx):\n    pass\n\nasync def run():\n    pass\n",
    ],
)
def test_automation_requires_context_argument(tmp_path: Path, source: str) -> None:
    (tmp_path / "automation.py").write_text(source)

    with pytest.raises(ConfigError, match="context argument"):
        load_automation(tmp_path)


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

    with pytest.raises(ConfigError, match="duplicate hardware pin"):
        validate_arduino_upload_config(tmp_path)


@pytest.mark.parametrize("tag_id", [None, True, 123])
def test_train_tag_id_must_be_a_string(tmp_path: Path, tag_id: object) -> None:
    _write_config(tmp_path)
    trains = json.loads((tmp_path / "trains.json").read_text())
    trains["trains"][0]["tag_id"] = tag_id
    (tmp_path / "trains.json").write_text(json.dumps(trains))

    with pytest.raises(ConfigError, match="tag_id must be a string"):
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


def test_reader_timeout_must_fit_uint16(tmp_path: Path) -> None:
    _write_config(tmp_path)
    devices = json.loads((tmp_path / "arduinos.json").read_text())
    devices["devices"]["arduino_1"]["readers"][0]["read_timeout_ms"] = 65536
    (tmp_path / "arduinos.json").write_text(json.dumps(devices))

    with pytest.raises(ConfigError, match="read_timeout_ms"):
        validate_arduino_upload_config(tmp_path)


def test_upload_only_fields_do_not_block_backend_config(tmp_path: Path) -> None:
    _write_config(tmp_path)
    devices = json.loads((tmp_path / "arduinos.json").read_text())
    devices["devices"]["arduino_1"]["port"] = ""
    (tmp_path / "arduinos.json").write_text(json.dumps(devices))

    load_runtime_config(tmp_path)
    with pytest.raises(ConfigError, match="port"):
        validate_arduino_upload_config(tmp_path)
