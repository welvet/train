#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


TESTS = Path(__file__).resolve().parent
FIRMWARE = TESTS.parent / "TrainController"
REPOSITORY = TESTS.parents[1]
FQBN = "arduino:renesas_uno:unor4wifi"


def run(command: list[str]) -> None:
    print(f"→ {' '.join(command)}", flush=True)
    subprocess.run(command, check=True)


def arduino_json_include() -> Path:
    result = subprocess.run(
        ["arduino-cli", "lib", "list", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    libraries = json.loads(result.stdout).get("installed_libraries", [])
    for installed in libraries:
        library = installed.get("library", {})
        if library.get("name") == "ArduinoJson":
            source = Path(library["source_dir"])
            if source.is_dir():
                return source
    raise SystemExit(
        "ArduinoJson is required; install it with "
        "`arduino-cli lib install ArduinoJson`."
    )


def run_host_tests(build: Path) -> None:
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
        str(arduino_json_include()),
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

    with tempfile.TemporaryDirectory(prefix="train-firmware-tests-") as directory:
        build = Path(directory)
        if not args.compile_only:
            run_host_tests(build)
        if not args.host_only:
            run_board_compile(build)


if __name__ == "__main__":
    main()
