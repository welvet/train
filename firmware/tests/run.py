#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


TESTS = Path(__file__).resolve().parent
FIRMWARE = TESTS.parent / "TrainController"
REPOSITORY = TESTS.parents[1]
sys.path.insert(0, str(REPOSITORY / "tools"))

from _arduino_cli import (  # noqa: E402
    ArduinoCliError,
    PN532_LIBRARY_NAME,
    PN532_LIBRARY_VERSION,
    installed_libraries,
    require_library_version,
)

FQBN = "arduino:renesas_uno:unor4wifi"


def run(command: list[str]) -> None:
    print(f"→ {' '.join(command)}", flush=True)
    subprocess.run(command, check=True)


def arduino_json_include(libraries: list[dict[str, Any]]) -> Path:
    for installed in libraries:
        library = installed.get("library")
        if not isinstance(library, dict):
            continue
        if library.get("name") == "ArduinoJson":
            source_dir = library.get("source_dir")
            if not isinstance(source_dir, str):
                continue
            source = Path(source_dir)
            if source.is_dir():
                return source
    raise SystemExit(
        "ArduinoJson is required; install it with "
        "`arduino-cli lib install ArduinoJson`."
    )


def run_host_tests(build: Path, libraries: list[dict[str, Any]]) -> None:
    compiler = shutil.which("c++") or shutil.which("g++")
    if compiler is None:
        raise SystemExit("A C++17 compiler is required for firmware tests.")
    binary = build / "firmware-tests"
    sources = sorted(FIRMWARE.glob("*.cpp"))
    command = [
        compiler,
        "-std=c++17",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-pedantic",
        "-I",
        str(TESTS / "stubs"),
        "-I",
        str(TESTS / "fixtures"),
        "-I",
        str(FIRMWARE),
        "-isystem",
        str(arduino_json_include(libraries)),
        *(str(source) for source in sources),
        str(TESTS / "firmware_tests.cpp"),
        "-o",
        str(binary),
    ]
    run(command)
    run([str(binary)])


def run_board_compile(build: Path) -> None:
    sketch = build / "TrainController"
    shutil.copytree(FIRMWARE, sketch)
    shutil.copy2(TESTS / "fixtures" / "generated_config.h", sketch)
    run(["arduino-cli", "compile", "--fqbn", FQBN, str(sketch)])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run native firmware tests and compile the production sketch"
    )
    parser.add_argument(
        "--host-only", action="store_true", help="skip the Arduino board compile"
    )
    parser.add_argument(
        "--compile-only", action="store_true", help="skip the native test binary"
    )
    args = parser.parse_args()
    if args.host_only and args.compile_only:
        parser.error("--host-only and --compile-only cannot be combined")

    try:
        libraries = installed_libraries()
        require_library_version(
            libraries, PN532_LIBRARY_NAME, PN532_LIBRARY_VERSION
        )
        with tempfile.TemporaryDirectory(prefix="train-firmware-tests-") as directory:
            build = Path(directory)
            if not args.compile_only:
                run_host_tests(build, libraries)
            if not args.host_only:
                run_board_compile(build)
    except (ArduinoCliError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"Error: {exc}") from exc


if __name__ == "__main__":
    main()
