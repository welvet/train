from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from train.modules.arduino_hub.timing import MAX_READER_READ_TIMEOUT_MS
from train.modules.arduino_hub.protocol import (
    MAX_COMPONENTS,
    MAX_ID_BYTES,
    encode_configuration,
    validate_hello_frame_size,
)


class ConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TrainConfig:
    train_id: str
    lego_hub_id: str
    ble_address: str
    tag_ids: tuple[str, ...]


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
    pin: int
    straight: int
    diverge: int


@dataclass(frozen=True, slots=True)
class ArduinoReaderConfig:
    reader_id: str
    ss_pin: int
    read_timeout_ms: int
    removal_delay_ms: int


@dataclass(frozen=True, slots=True)
class ArduinoDeviceConfig:
    device_id: str
    hub_id: str
    servo_settle_ms: int
    switches: tuple[ArduinoSwitchConfig, ...]
    readers: tuple[ArduinoReaderConfig, ...]
    allow_legacy_hello: bool


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
            tag_id: train.train_id
            for train in self.trains
            for tag_id in train.tag_ids
        }

    @property
    def arduino_hubs(self) -> dict[str, dict[str, Any]]:
        return {
            device.hub_id: {
                "device_id": device.device_id,
                "switches": {
                    switch.switch_id: {
                        "pin": switch.pin,
                        "straight": switch.straight,
                        "diverge": switch.diverge,
                    }
                    for switch in device.switches
                },
                "detectors": tuple(reader.reader_id for reader in device.readers),
                "servo_settle_ms": device.servo_settle_ms,
                "readers": {
                    reader.reader_id: {
                        "ss_pin": reader.ss_pin,
                        "read_timeout_ms": reader.read_timeout_ms,
                        "removal_delay_ms": reader.removal_delay_ms,
                    }
                    for reader in device.readers
                },
                "allow_legacy_hello": device.allow_legacy_hello,
            }
            for device in self.arduinos
        }


def default_data_dir() -> Path:
    configured = os.environ.get("TRAIN_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data"


def default_automation_path() -> Path:
    configured = os.environ.get("TRAIN_AUTOMATIONS_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return default_data_dir() / "automations.json"


def default_trains_path() -> Path:
    configured = os.environ.get("TRAIN_TRAINS_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return default_data_dir() / "trains.json"


def default_arduinos_path() -> Path:
    configured = os.environ.get("TRAIN_ARDUINOS_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return default_data_dir() / "arduinos.json"


def load_runtime_config(data_dir: Path | None = None) -> RuntimeConfig:
    root = data_dir or default_data_dir()
    backend_data = _read_json(root / "backend.json")
    trains_data = _read_json(
        root / "trains.json" if data_dir is not None else default_trains_path()
    )
    arduinos_data = _read_json(
        root / "arduinos.json" if data_dir is not None else default_arduinos_path()
    )

    api = _mapping(backend_data, "api", "backend.json")
    arduino = _mapping(backend_data, "arduino_server", "backend.json")
    backend = BackendConfig(
        api_host=_string(api, "host", "backend.json"),
        api_port=_port(api, "port", "backend.json"),
        api_url=_string(api, "url", "backend.json").rstrip("/"),
        arduino_host=_string(arduino, "host", "backend.json"),
        arduino_port=_port(arduino, "port", "backend.json"),
    )

    trains = parse_trains_document(trains_data)

    devices = parse_arduinos_document(arduinos_data)

    runtime = RuntimeConfig(
        backend=backend,
        trains=trains,
        arduinos=devices,
    )
    _validate_arduino_protocol(runtime)
    return runtime


def parse_trains_document(trains_data: dict[str, Any]) -> tuple[TrainConfig, ...]:
    """Validate and normalize the editable trains.json document."""
    unexpected_root_fields = set(trains_data) - {"trains"}
    if unexpected_root_fields:
        raise ConfigError(
            "trains.json: unsupported field(s): "
            + ", ".join(sorted(unexpected_root_fields))
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
        unexpected_fields = set(value) - {
            "id",
            "lego_hub_id",
            "ble_address",
            "tag_id",
            "tag_ids",
        }
        if unexpected_fields:
            raise ConfigError(
                f"{source}: unsupported field(s): "
                + ", ".join(sorted(unexpected_fields))
            )
        train_id = _string(value, "id", source)
        raw_lego_hub_id = value.get("lego_hub_id", train_id)
        if not isinstance(raw_lego_hub_id, str) or not raw_lego_hub_id.strip():
            raise ConfigError(f"{source}.lego_hub_id must be a non-empty string")
        lego_hub_id = raw_lego_hub_id.strip()
        ble_address = _string(value, "ble_address", source)
        normalized_tag_ids = _train_tag_ids(value, source)
        _unique(train_id, train_ids, f"{source}.id")
        _unique(lego_hub_id, lego_hub_ids, f"{source}.lego_hub_id")
        _unique(ble_address, ble_addresses, f"{source}.ble_address")
        for tag_index, tag_id in enumerate(normalized_tag_ids):
            tag_source = (
                f"{source}.tag_ids[{tag_index}]"
                if "tag_ids" in value
                else f"{source}.tag_id"
            )
            _unique(tag_id, tag_ids, tag_source)
        trains.append(TrainConfig(
            train_id,
            lego_hub_id,
            ble_address,
            normalized_tag_ids,
        ))

    return tuple(trains)


def normalized_trains_document(
    trains_data: dict[str, Any],
) -> dict[str, list[dict[str, object]]]:
    """Return the stable on-disk representation used by the configuration API."""
    return {
        "trains": [
            {
                "id": train.train_id,
                "lego_hub_id": train.lego_hub_id,
                "ble_address": train.ble_address,
                "tag_ids": list(train.tag_ids),
            }
            for train in parse_trains_document(trains_data)
        ]
    }


def parse_arduinos_document(
    arduinos_data: dict[str, Any],
) -> tuple[ArduinoDeviceConfig, ...]:
    unexpected_root_fields = set(arduinos_data) - {"devices"}
    if unexpected_root_fields:
        raise ConfigError(
            "arduinos.json: unsupported field(s): "
            + ", ".join(sorted(unexpected_root_fields))
        )
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
        unexpected_fields = set(value) - {
            "port",
            "fqbn",
            "baudrate",
            "hub_id",
            "backend_host",
            "backend_port",
            "servo_settle_ms",
            "reconnect_ms",
            "event_logger_enabled",
            "allow_legacy_hello",
            "switches",
            "readers",
        }
        if unexpected_fields:
            raise ConfigError(
                f"{source}: unsupported field(s): "
                + ", ".join(sorted(unexpected_fields))
            )
        normalized_device_id = _runtime_id(device_id, "arduinos.json: device ID")
        hub_id = _runtime_id(_string(value, "hub_id", source), f"{source}.hub_id")
        _unique(hub_id, hub_ids, f"{source}.hub_id")
        servo_settle_ms = _bounded_int(
            value, "servo_settle_ms", source, maximum=0xFFFFFFFF
        )
        allow_legacy_hello = value.get("allow_legacy_hello", True)
        if not isinstance(allow_legacy_hello, bool):
            raise ConfigError(f"{source}.allow_legacy_hello must be a boolean")
        component_ids: set[str] = set()
        pins: set[int] = set()
        switches: list[ArduinoSwitchConfig] = []
        for index, switch in enumerate(_list(value, "switches", source)):
            item_source = f"{source}.switches[{index}]"
            if not isinstance(switch, dict):
                raise ConfigError(f"{item_source} must be an object")
            unexpected_fields = set(switch) - {"id", "pin", "straight", "diverge"}
            if unexpected_fields:
                raise ConfigError(
                    f"{item_source}: unsupported field(s): "
                    + ", ".join(sorted(unexpected_fields))
                )
            switch_id = _runtime_id(
                _string(switch, "id", item_source), f"{item_source}.id"
            )
            _unique(switch_id, component_ids, f"{item_source}.id")
            pin = _runtime_pin(switch, "pin", item_source, pins)
            angles: list[int] = []
            for key in ("straight", "diverge"):
                angle = switch.get(key)
                if not isinstance(angle, int) or isinstance(angle, bool) or not 0 <= angle <= 180:
                    raise ConfigError(f"{item_source}.{key} must be in 0..180")
                angles.append(angle)
            switches.append(ArduinoSwitchConfig(switch_id, pin, *angles))
        readers: list[ArduinoReaderConfig] = []
        for index, reader in enumerate(_list(value, "readers", source)):
            item_source = f"{source}.readers[{index}]"
            if not isinstance(reader, dict):
                raise ConfigError(f"{item_source} must be an object")
            unexpected_fields = set(reader) - {
                "id",
                "ss_pin",
                "read_timeout_ms",
                "removal_delay_ms",
            }
            if unexpected_fields:
                raise ConfigError(
                    f"{item_source}: unsupported field(s): "
                    + ", ".join(sorted(unexpected_fields))
                )
            reader_id = _runtime_id(
                _string(reader, "id", item_source), f"{item_source}.id"
            )
            _unique(reader_id, component_ids, f"{item_source}.id")
            ss_pin = _runtime_pin(reader, "ss_pin", item_source, pins)
            read_timeout_ms = _bounded_int(
                reader,
                "read_timeout_ms",
                item_source,
                maximum=MAX_READER_READ_TIMEOUT_MS,
            )
            removal_delay_ms = _bounded_int(
                reader, "removal_delay_ms", item_source, maximum=0xFFFFFFFF
            )
            readers.append(ArduinoReaderConfig(
                reader_id, ss_pin, read_timeout_ms, removal_delay_ms
            ))
        if len(switches) > MAX_COMPONENTS:
            raise ConfigError(
                f"{source}.switches supports at most {MAX_COMPONENTS} entries"
            )
        if len(readers) > MAX_COMPONENTS:
            raise ConfigError(
                f"{source}.readers supports at most {MAX_COMPONENTS} entries"
            )
        devices.append(ArduinoDeviceConfig(
            normalized_device_id,
            hub_id,
            servo_settle_ms,
            tuple(switches),
            tuple(readers),
            allow_legacy_hello,
        ))

    return tuple(devices)


def normalized_arduinos_document(
    arduinos_data: dict[str, Any],
) -> dict[str, dict[str, dict[str, object]]]:
    """Validate and return the stable editable representation of arduinos.json."""
    devices = parse_arduinos_document(arduinos_data)
    raw_devices = _mapping(arduinos_data, "devices", "arduinos.json")
    normalized: dict[str, dict[str, object]] = {}
    for device in devices:
        raw = raw_devices[device.device_id]
        source = f"arduinos.json: devices.{device.device_id}"
        port = _string(raw, "port", source)
        fqbn = _string(raw, "fqbn", source)
        baudrate = _bounded_int(raw, "baudrate", source, maximum=0xFFFFFFFF)
        backend_host = _string(raw, "backend_host", source)
        backend_port = _port(raw, "backend_port", source)
        reconnect_ms = _bounded_int(
            raw, "reconnect_ms", source, maximum=0xFFFFFFFF
        )
        event_logger_enabled = raw.get("event_logger_enabled", False)
        if not isinstance(event_logger_enabled, bool):
            raise ConfigError(f"{source}.event_logger_enabled must be a boolean")
        normalized[device.device_id] = {
            "port": port,
            "fqbn": fqbn,
            "baudrate": baudrate,
            "hub_id": device.hub_id,
            "backend_host": backend_host,
            "backend_port": backend_port,
            "servo_settle_ms": device.servo_settle_ms,
            "reconnect_ms": reconnect_ms,
            "event_logger_enabled": event_logger_enabled,
            "allow_legacy_hello": device.allow_legacy_hello,
            "switches": [
                {
                    "id": switch.switch_id,
                    "pin": switch.pin,
                    "straight": switch.straight,
                    "diverge": switch.diverge,
                }
                for switch in device.switches
            ],
            "readers": [
                {
                    "id": reader.reader_id,
                    "ss_pin": reader.ss_pin,
                    "read_timeout_ms": reader.read_timeout_ms,
                    "removal_delay_ms": reader.removal_delay_ms,
                }
                for reader in device.readers
            ],
        }
    runtime = RuntimeConfig(
        backend=BackendConfig("", 1, "", "", 1),
        trains=(),
        arduinos=devices,
    )
    _validate_arduino_protocol(runtime)
    return {"devices": normalized}


def runtime_config_from_documents(
    base: RuntimeConfig,
    *,
    trains: dict[str, Any],
    arduinos: dict[str, Any],
) -> RuntimeConfig:
    """Build and validate the runtime represented by persisted editable documents."""
    runtime = replace(
        base,
        trains=parse_trains_document(trains),
        arduinos=parse_arduinos_document(arduinos),
    )
    _validate_arduino_protocol(runtime)
    return runtime


def _train_tag_ids(value: dict[str, Any], source: str) -> tuple[str, ...]:
    if "tag_id" in value and "tag_ids" in value:
        raise ConfigError(f"{source} must not define both tag_id and tag_ids")

    if "tag_ids" in value:
        raw_tag_ids = value["tag_ids"]
        if not isinstance(raw_tag_ids, list):
            raise ConfigError(f"{source}.tag_ids must be a list")
        normalized: list[str] = []
        for index, raw_tag_id in enumerate(raw_tag_ids):
            if not isinstance(raw_tag_id, str) or not raw_tag_id.strip():
                raise ConfigError(
                    f"{source}.tag_ids[{index}] must be a non-empty string"
                )
            normalized.append(raw_tag_id.strip().upper())
        return tuple(normalized)

    raw_tag_id = value.get("tag_id", "")
    if not isinstance(raw_tag_id, str):
        raise ConfigError(f"{source}.tag_id must be a string")
    normalized_legacy_tag_id = raw_tag_id.strip().upper()
    return (normalized_legacy_tag_id,) if normalized_legacy_tag_id else ()


def validate_arduino_upload_config(data_dir: Path | None = None) -> None:
    root = data_dir or default_data_dir()
    load_runtime_config(root)
    normalized_arduinos_document(_read_json(root / "arduinos.json"))


def _validate_arduino_protocol(runtime: RuntimeConfig) -> None:
    for hub_id, hub_config in runtime.arduino_hubs.items():
        try:
            encode_configuration(hub_id, hub_config)
            validate_hello_frame_size(hub_id, hub_config)
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc


def _runtime_pin(
    value: dict[str, Any], key: str, source: str, seen: set[int]
) -> int:
    pin = _bounded_int(value, key, source, maximum=10)
    if pin < 2:
        raise ConfigError(f"{source}.{key} must be a digital pin in D2..D10")
    if pin in seen:
        raise ConfigError(f"{source}.{key} duplicates pin D{pin}")
    seen.add(pin)
    return pin


def _runtime_id(value: str, source: str) -> str:
    if len(value.encode("utf-8")) > MAX_ID_BYTES:
        raise ConfigError(f"{source} must be at most {MAX_ID_BYTES} bytes")
    if re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise ConfigError(
            f"{source} may contain only letters, digits, underscores, and hyphens"
        )
    return value


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


def _unique(value: str, seen: set[str], source: str) -> None:
    if value in seen:
        raise ConfigError(f"{source}: duplicate value '{value}'")
    seen.add(value)
