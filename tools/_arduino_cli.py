from __future__ import annotations

import json
import subprocess
from typing import Any

PN532_LIBRARY_NAME = "Adafruit PN532"
PN532_LIBRARY_VERSION = "1.3.4"


class ArduinoCliError(RuntimeError):
    pass


def installed_libraries() -> list[dict[str, Any]]:
    try:
        result = subprocess.run(
            ["arduino-cli", "lib", "list", "--format", "json"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ArduinoCliError("arduino-cli is required but was not found") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        message = "arduino-cli failed to list installed libraries"
        raise ArduinoCliError(f"{message}: {detail}" if detail else message) from exc

    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ArduinoCliError(
            "arduino-cli returned invalid JSON while listing installed libraries"
        ) from exc
    if not isinstance(document, dict):
        raise ArduinoCliError(
            "arduino-cli returned an invalid installed library inventory"
        )
    libraries = document.get("installed_libraries", [])
    if libraries is None:
        libraries = []
    if not isinstance(libraries, list) or not all(
        isinstance(installed, dict) for installed in libraries
    ):
        raise ArduinoCliError(
            "arduino-cli returned an invalid installed library inventory"
        )
    return libraries


def require_library_version(
    libraries: list[dict[str, Any]], name: str, version: str
) -> None:
    installed_version: object | None = None
    for installed in libraries:
        library = installed.get("library")
        if not isinstance(library, dict) or library.get("name") != name:
            continue
        installed_version = library.get("version")
        if installed_version == version:
            return

    detail = (
        f", but version {installed_version} is installed"
        if isinstance(installed_version, str)
        else ""
    )
    raise ArduinoCliError(
        f"{name} {version} is required{detail}; install it with "
        f"`arduino-cli lib install '{name}@{version}'`."
    )
