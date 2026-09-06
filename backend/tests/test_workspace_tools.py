from __future__ import annotations

import importlib.machinery
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import _arduino_cli  # noqa: E402


def _load_tool(name: str) -> ModuleType:
    path = TOOLS / name
    loader = importlib.machinery.SourceFileLoader(f"test_tool_{name}", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_data_initializer_creates_isolated_workspace_scaffold(
    tmp_path: Path,
) -> None:
    data_tool = _load_tool("data")

    data_tool.init_workspace(tmp_path)

    assert (tmp_path / "secrets.json").stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "trains.json").read_text().strip() == '{\n  "trains": []\n}'
    deployment = (tmp_path / "deployment.json").read_text()
    assert '"remote_dir": "/train/deploy"' in deployment
    assert (tmp_path / "automations.json").read_text() == (
        '{\n  "version": 3,\n  "rules": []\n}\n'
    )


def test_generated_firmware_config_supports_multiple_devices() -> None:
    arduino_tool = _load_tool("arduino")
    device = {
        "device_id": "arduino_1",
        "hub_id": "hub_1",
        "backend_host": "host",
        "backend_port": 9000,
        "baudrate": 115200,
        "servo_settle_ms": 500,
        "reconnect_ms": 2000,
        "event_logger_enabled": True,
        "switches": [
            {"id": "S1", "pin": 9, "straight": 58, "diverge": 100},
            {"id": "S2", "pin": 10, "straight": 60, "diverge": 110},
        ],
        "readers": [
            {"id": "D1", "ss_pin": 4, "read_timeout_ms": 250, "removal_delay_ms": 750},
            {"id": "D2", "ss_pin": 5, "read_timeout_ms": 200, "removal_delay_ms": 800},
        ],
    }

    result = arduino_tool.generate_config(
        device, {"wifi_ssid": "wifi", "wifi_password": "secret"}
    )

    assert 'constexpr char DEVICE_ID[] = "arduino_1";' in result
    assert "constexpr bool EVENT_LOGGER_ENABLED = true;" in result
    assert "SWITCH_COUNT" not in result
    assert "READER_COUNT" not in result
    assert "D1" not in result


def test_generated_firmware_config_disables_event_logger_by_default() -> None:
    arduino_tool = _load_tool("arduino")
    device = {
        "device_id": "arduino_1",
        "hub_id": "hub_1",
        "backend_host": "host",
        "backend_port": 9000,
        "baudrate": 115200,
        "servo_settle_ms": 500,
        "reconnect_ms": 2000,
        "switches": [],
        "readers": [],
    }

    result = arduino_tool.generate_config(
        device, {"wifi_ssid": "wifi", "wifi_password": "secret"}
    )

    assert "constexpr bool EVENT_LOGGER_ENABLED = false;" in result


def test_arduino_tool_accepts_supported_pn532_library_version() -> None:
    _arduino_cli.require_library_version(
        [{"library": {"name": "Adafruit PN532", "version": "1.3.4"}}],
        "Adafruit PN532",
        "1.3.4",
    )


@pytest.mark.parametrize(
    "libraries",
    [[], [{"library": {"name": "Adafruit PN532", "version": "1.4.0"}}]],
)
def test_arduino_tool_requires_supported_pn532_library_version(
    libraries: list[dict[str, object]],
) -> None:
    with pytest.raises(_arduino_cli.ArduinoCliError, match="1.3.4 is required"):
        _arduino_cli.require_library_version(
            libraries,
            "Adafruit PN532",
            "1.3.4",
        )


def test_arduino_library_inventory_reports_cli_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise subprocess.CalledProcessError(
            1, ["arduino-cli"], stderr="index unavailable"
        )

    monkeypatch.setattr(_arduino_cli.subprocess, "run", fail)

    with pytest.raises(
        _arduino_cli.ArduinoCliError,
        match="failed to list installed libraries: index unavailable",
    ):
        _arduino_cli.installed_libraries()


def test_arduino_library_inventory_reports_missing_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("arduino-cli")

    monkeypatch.setattr(_arduino_cli.subprocess, "run", fail)

    with pytest.raises(_arduino_cli.ArduinoCliError, match="was not found"):
        _arduino_cli.installed_libraries()


@pytest.mark.parametrize("output", ["not-json", "[]"])
def test_arduino_library_inventory_rejects_invalid_output(
    monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    completed = subprocess.CompletedProcess(
        ["arduino-cli"], returncode=0, stdout=output, stderr=""
    )
    monkeypatch.setattr(
        _arduino_cli.subprocess,
        "run",
        lambda *args, **kwargs: completed,
    )

    with pytest.raises(_arduino_cli.ArduinoCliError, match="invalid"):
        _arduino_cli.installed_libraries()
