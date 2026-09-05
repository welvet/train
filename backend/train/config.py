from __future__ import annotations

import importlib.util
import inspect
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from train.modules.arduino_hub.timing import MAX_READER_READ_TIMEOUT_MS
from train.modules.automation import ConfigureFn, ScriptFn


class ConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TrainConfig:
    train_id: str
    lego_hub_id: str
    ble_address: str
    tag_id: str


@dataclass(frozen=True, slots=True)
class BackendConfig:
    api_host: str
    api_port: int
    api_url: str
    arduino_host: str
    arduino_port: int


@dataclass(frozen=True, slots=True)
class ArduinoSwitchConfig:
    switch_id: str
    straight: int
    diverge: int


@dataclass(frozen=True, slots=True)
class ArduinoDeviceConfig:
    device_id: str
    hub_id: str
    switches: tuple[ArduinoSwitchConfig, ...]
    readers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AutomationProgram:
    configure: ConfigureFn
    run: ScriptFn


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    backend: BackendConfig
    trains: tuple[TrainConfig, ...]
    arduinos: tuple[ArduinoDeviceConfig, ...]

    @property
    def train_map(self) -> dict[str, str]:
        return {train.ble_address: train.train_id for train in self.trains}

    @property
    def train_tag_map(self) -> dict[str, str]:
        return {
            train.tag_id: train.train_id
            for train in self.trains
            if train.tag_id
        }

    @property
    def arduino_hubs(self) -> dict[str, dict[str, Any]]:
        return {
            device.hub_id: {
                "device_id": device.device_id,
                "switches": {
                    switch.switch_id: {
                        "straight": switch.straight,
                        "diverge": switch.diverge,
                    }
                    for switch in device.switches
                },
                "detectors": device.readers,
            }
            for device in self.arduinos
        }


def default_data_dir() -> Path:
    configured = os.environ.get("TRAIN_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data"


def load_runtime_config(data_dir: Path | None = None) -> RuntimeConfig:
    root = data_dir or default_data_dir()
    backend_data = _read_json(root / "backend.json")
    trains_data = _read_json(root / "trains.json")
    arduinos_data = _read_json(root / "arduinos.json")

    api = _mapping(backend_data, "api", "backend.json")
    arduino = _mapping(backend_data, "arduino_server", "backend.json")
    backend = BackendConfig(
        api_host=_string(api, "host", "backend.json"),
        api_port=_port(api, "port", "backend.json"),
        api_url=_string(api, "url", "backend.json").rstrip("/"),
        arduino_host=_string(arduino, "host", "backend.json"),
        arduino_port=_port(arduino, "port", "backend.json"),
    )

    raw_trains = trains_data.get("trains")
    if not isinstance(raw_trains, list) or not raw_trains:
        raise ConfigError("trains.json: 'trains' must be a non-empty list")

    trains: list[TrainConfig] = []
    train_ids: set[str] = set()
    lego_hub_ids: set[str] = set()
    ble_addresses: set[str] = set()
    tag_ids: set[str] = set()
    for index, value in enumerate(raw_trains):
        source = f"trains.json: trains[{index}]"
        if not isinstance(value, dict):
            raise ConfigError(f"{source} must be an object")
        train_id = _string(value, "id", source)
        raw_lego_hub_id = value.get("lego_hub_id", train_id)
        if not isinstance(raw_lego_hub_id, str) or not raw_lego_hub_id.strip():
            raise ConfigError(f"{source}.lego_hub_id must be a non-empty string")
        lego_hub_id = raw_lego_hub_id.strip()
        ble_address = _string(value, "ble_address", source)
        raw_tag_id = value.get("tag_id", "")
        if not isinstance(raw_tag_id, str):
            raise ConfigError(f"{source}.tag_id must be a string")
        tag_id = raw_tag_id.strip().upper()
        _unique(train_id, train_ids, f"{source}.id")
        _unique(lego_hub_id, lego_hub_ids, f"{source}.lego_hub_id")
        _unique(ble_address, ble_addresses, f"{source}.ble_address")
        if tag_id:
            _unique(tag_id, tag_ids, f"{source}.tag_id")
        trains.append(TrainConfig(train_id, lego_hub_id, ble_address, tag_id))

    raw_devices = _mapping(arduinos_data, "devices", "arduinos.json")
    if not raw_devices:
        raise ConfigError("arduinos.json: 'devices' must not be empty")
    devices: list[ArduinoDeviceConfig] = []
    hub_ids: set[str] = set()
    for device_id, value in raw_devices.items():
        source = f"arduinos.json: devices.{device_id}"
        if not isinstance(device_id, str) or not device_id.strip():
            raise ConfigError("arduinos.json: device IDs must be non-empty strings")
        if not isinstance(value, dict):
            raise ConfigError(f"{source} must be an object")
        hub_id = _string(value, "hub_id", source)
        _unique(hub_id, hub_ids, f"{source}.hub_id")
        component_ids: set[str] = set()
        switches: list[ArduinoSwitchConfig] = []
        for index, switch in enumerate(_list(value, "switches", source)):
            item_source = f"{source}.switches[{index}]"
            if not isinstance(switch, dict):
                raise ConfigError(f"{item_source} must be an object")
            switch_id = _string(switch, "id", item_source)
            _unique(switch_id, component_ids, f"{item_source}.id")
            angles: list[int] = []
            for key in ("straight", "diverge"):
                angle = switch.get(key)
                if not isinstance(angle, int) or isinstance(angle, bool) or not 0 <= angle <= 180:
                    raise ConfigError(f"{item_source}.{key} must be in 0..180")
                angles.append(angle)
            switches.append(ArduinoSwitchConfig(switch_id, *angles))
        reader_ids = _validate_component_ids(
            value, "readers", source, component_ids
        )
        devices.append(ArduinoDeviceConfig(
            device_id.strip(), hub_id, tuple(switches), reader_ids
        ))

    return RuntimeConfig(
        backend=backend,
        trains=tuple(trains),
        arduinos=tuple(devices),
    )


def validate_arduino_upload_config(data_dir: Path | None = None) -> None:
    root = data_dir or default_data_dir()
    load_runtime_config(root)
    devices = _mapping(_read_json(root / "arduinos.json"), "devices", "arduinos.json")
    for device_id, device in devices.items():
        if not isinstance(device, dict):
            raise ConfigError(
                f"arduinos.json: devices.{device_id} must be an object"
            )
        source = f"arduinos.json: devices.{device_id}"
        for key in ("port", "fqbn", "backend_host"):
            _string(device, key, source)
        _bounded_int(device, "baudrate", source, maximum=0xFFFFFFFF)
        _port(device, "backend_port", source)
        for key in ("servo_settle_ms", "reconnect_ms"):
            _bounded_int(device, key, source, maximum=0xFFFFFFFF)
        logger_enabled = device.get("event_logger_enabled", False)
        if not isinstance(logger_enabled, bool):
            raise ConfigError(
                f"{source}.event_logger_enabled must be a boolean"
            )
        pins: set[int] = set()
        _validate_component_pins(device, "switches", "pin", source, pins)
        _validate_component_pins(device, "readers", "ss_pin", source, pins)
        for index, reader in enumerate(_list(device, "readers", source)):
            reader_source = f"{source}.readers[{index}]"
            if not isinstance(reader, dict):
                raise ConfigError(f"{reader_source} must be an object")
            _bounded_int(
                reader,
                "read_timeout_ms",
                reader_source,
                maximum=MAX_READER_READ_TIMEOUT_MS,
            )
            _bounded_int(
                reader, "removal_delay_ms", reader_source, maximum=0xFFFFFFFF
            )


def load_automation(data_dir: Path | None = None) -> AutomationProgram:
    root = data_dir or default_data_dir()
    path = root / "automation.py"
    if not path.is_file():
        raise ConfigError(
            f"Missing {path}. Create the workspace with 'tools/data init'."
        )
    module_name = "train_workspace_automation"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ConfigError(f"Cannot load automation script from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise ConfigError(f"Cannot load {path}: {exc}") from exc
    configure = getattr(module, "configure", None)
    script = getattr(module, "run", None)
    if not callable(configure) or inspect.iscoroutinefunction(configure):
        raise ConfigError(f"{path} must export synchronous def configure(ctx)")
    if not inspect.iscoroutinefunction(script):
        raise ConfigError(f"{path} must export async def run(ctx)")
    _validate_context_signature(configure, path, "configure")
    _validate_context_signature(script, path, "run")
    return AutomationProgram(configure=configure, run=script)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise ConfigError(
            f"Missing {path}. Create the workspace with 'tools/data init'."
        ) from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ConfigError(f"{path}: root must be an object")
    return value


def _mapping(value: dict[str, Any], key: str, source: str) -> dict[str, Any]:
    result = value.get(key)
    if not isinstance(result, dict):
        raise ConfigError(f"{source}: '{key}' must be an object")
    return result


def _string(value: dict[str, Any], key: str, source: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ConfigError(f"{source}: '{key}' must be a non-empty string")
    return result.strip()


def _port(value: dict[str, Any], key: str, source: str) -> int:
    result = value.get(key)
    if not isinstance(result, int) or isinstance(result, bool) or not 1 <= result <= 65535:
        raise ConfigError(f"{source}: '{key}' must be a port in 1..65535")
    return result


def _bounded_int(
    value: dict[str, Any], key: str, source: str, *, maximum: int
) -> int:
    result = value.get(key)
    if (
        not isinstance(result, int)
        or isinstance(result, bool)
        or not 1 <= result <= maximum
    ):
        raise ConfigError(f"{source}: '{key}' must be in 1..{maximum}")
    return result


def _list(value: dict[str, Any], key: str, source: str) -> list[Any]:
    result = value.get(key)
    if not isinstance(result, list):
        raise ConfigError(f"{source}: '{key}' must be a list")
    return result


def _validate_component_ids(
    device: dict[str, Any],
    collection: str,
    source: str,
    component_ids: set[str],
) -> tuple[str, ...]:
    ids: list[str] = []
    for index, component in enumerate(_list(device, collection, source)):
        item_source = f"{source}.{collection}[{index}]"
        if not isinstance(component, dict):
            raise ConfigError(f"{item_source} must be an object")
        component_id = _string(component, "id", item_source)
        _unique(component_id, component_ids, f"{item_source}.id")
        ids.append(component_id)
    return tuple(ids)


def _validate_component_pins(
    device: dict[str, Any],
    collection: str,
    pin_key: str,
    source: str,
    pins: set[int],
) -> None:
    for index, component in enumerate(_list(device, collection, source)):
        item_source = f"{source}.{collection}[{index}]"
        if not isinstance(component, dict):
            raise ConfigError(f"{item_source} must be an object")
        pin = component.get(pin_key)
        if not isinstance(pin, int) or isinstance(pin, bool) or not 0 <= pin <= 255:
            raise ConfigError(f"{item_source}.{pin_key} must be a pin in 0..255")
        if pin in pins:
            raise ConfigError(
                f"{item_source}.{pin_key}: duplicate hardware pin '{pin}'"
            )
        pins.add(pin)


def _unique(value: str, seen: set[str], source: str) -> None:
    if value in seen:
        raise ConfigError(f"{source}: duplicate value '{value}'")
    seen.add(value)


def _validate_context_signature(function: Any, path: Path, name: str) -> None:
    try:
        inspect.signature(function).bind(object())
    except TypeError as exc:
        raise ConfigError(f"{path}: {name} must accept one context argument") from exc
