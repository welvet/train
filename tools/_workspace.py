from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


class WorkspaceError(ValueError):
    pass


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"


def data_dir() -> Path:
    configured = os.environ.get("TRAIN_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return REPO_ROOT / "data"


def read_json(name: str, root: Path | None = None) -> dict[str, Any]:
    path = (root or data_dir()) / name
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise WorkspaceError(
            f"Missing {path}. Create it with 'tools/data init'."
        ) from exc
    except json.JSONDecodeError as exc:
        raise WorkspaceError(f"{path}: invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise WorkspaceError(f"{path}: root must be an object")
    return value


def backend_url(root: Path | None = None) -> str:
    backend = read_json("backend.json", root)
    api = _object(backend, "api", "backend.json")
    return _string(api, "url", "backend.json").rstrip("/")


def arduino_device(device_id: str, root: Path | None = None) -> dict[str, Any]:
    workspace = root or data_dir()
    _validate_runtime_config(workspace)
    devices_data = read_json("arduinos.json", workspace)
    devices = _object(devices_data, "devices", "arduinos.json")
    device = devices.get(device_id)
    if not isinstance(device, dict):
        available = ", ".join(sorted(devices)) or "none"
        raise WorkspaceError(
            f"Unknown Arduino '{device_id}'. Configured devices: {available}"
        )
    return device


def arduino_secrets(device_id: str, root: Path | None = None) -> dict[str, str]:
    secrets_data = read_json("secrets.json", root)
    devices = _object(secrets_data, "devices", "secrets.json")
    secrets = devices.get(device_id)
    if not isinstance(secrets, dict):
        raise WorkspaceError(f"secrets.json: missing device '{device_id}'")
    return {
        "wifi_ssid": _string(secrets, "wifi_ssid", f"secrets.json:{device_id}"),
        "wifi_password": _string(
            secrets, "wifi_password", f"secrets.json:{device_id}"
        ),
    }


def validate_workspace(root: Path | None = None) -> None:
    workspace = root or data_dir()
    runtime = _validate_runtime_config(workspace)
    devices_data = read_json("arduinos.json", workspace)
    devices = _object(devices_data, "devices", "arduinos.json")
    for device in runtime.arduinos:
        assert device.device_id in devices
        arduino_secrets(device.device_id, workspace)

    automation = workspace / "automation.py"
    if not automation.is_file():
        raise WorkspaceError(f"Missing {automation}")
    validate_automation(workspace)


def validate_automation(root: Path) -> None:
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from train.config import ConfigError, load_automation

    try:
        load_automation(root)
    except ConfigError as exc:
        raise WorkspaceError(str(exc)) from exc


def _validate_runtime_config(root: Path):
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from train.config import (
        ConfigError,
        load_runtime_config,
        validate_arduino_upload_config,
    )

    try:
        runtime = load_runtime_config(root)
        validate_arduino_upload_config(root)
        return runtime
    except ConfigError as exc:
        raise WorkspaceError(str(exc)) from exc


def _object(value: dict[str, Any], key: str, source: str) -> dict[str, Any]:
    result = value.get(key)
    if not isinstance(result, dict):
        raise WorkspaceError(f"{source}: '{key}' must be an object")
    return result


def _string(value: dict[str, Any], key: str, source: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise WorkspaceError(f"{source}: '{key}' must be a non-empty string")
    return result.strip()
