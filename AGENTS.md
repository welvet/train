# Repository instructions

## Project overview

This repository contains reusable Arduino firmware and a Python backend for a
configurable LEGO model railway. Repository code is fixed product logic; one
installation lives in the ignored `data/` workspace documented in `DATA.md`.

### Structure

- `backend/` — event bus, hardware modules, web API, and automation runtime
- `firmware/TrainController/` — generic UNO R4 WiFi firmware
- `tools/` — workspace, firmware, control, and FTP deployment commands
- `web/` — statically exported Next.js and TypeScript UI
- `data/` — ignored local configuration, secrets, and automation
- `DATA.md` — workspace schema and operator guide

## Local workspace safety

The tracked repository is reusable product code. The top-level `data/`
directory is the operator's local railway workspace and is intentionally
excluded from Git.

- Do not search, list, inspect, test, lint, review, stage, or commit anything
  under `data/` unless the user explicitly asks to work with workspace data.
- Never copy values from `data/` into tracked files, logs, test fixtures, PRs,
  or responses. It may contain device identifiers and credentials.
- Tests must create isolated temporary configurations; they must never depend
  on or mutate the real `data/` directory.
- Product code belongs in `backend/`, `firmware/`, `tools/`, and `web/`. Runtime
  choices—trains, Arduino devices, track automation, and secrets—belong only
  in `data/`.
- `deploy/`, `releases/`, and `current` are server-loop runtime state. They are
  ignored and must never be staged or treated as source.
- See `DATA.md` for the workspace schema and supported commands.

Initialize or validate a workspace with:

```sh
tools/data init
tools/data validate
```

Set `TRAIN_DATA_DIR` to use a workspace outside the repository. Backend startup
fails with a guided error when required data is absent or invalid.

## Firmware

`firmware/TrainController/TrainController.ino` contains no installation values.
`tools/arduino` selects a named device from `data/arduinos.json`, validates all
switch and PN532 reader IDs and pins, generates `generated_config.h` in a
temporary sketch, then calls Arduino CLI.

```sh
tools/arduino list
tools/arduino compile arduino_1
tools/arduino upload arduino_1
tools/arduino monitor arduino_1
```

Multiple switches and PN532 readers are supported per device. Readers share the
hardware SPI bus and use separate SS pins. A failed reader is omitted from the
hello handshake while switches and healthy readers continue operating.

### Arduino TCP protocol

Messages use newline-delimited JSON:

- `hello`: hub ID, switch IDs, healthy detector IDs, and authoritative active
  tags
- `tag_detected`: hub, detector ID, and raw tag UID
- `tag_removed`: hub, detector ID, and raw tag UID
- `move_ack`: switch command result
- `pong`: health response

The backend resolves raw UIDs to train IDs using `data/trains.json`; firmware
never contains train identity.

## Backend

The backend is a Python 3.11+ asyncio application using `bleak` and `aiohttp`.

- `train/config.py` validates local backend and train configuration and loads
  the programmable `data/automation.py` entry point.
- `train/modules/lego_ble.py` manages configured LEGO hubs.
- `train/modules/arduino_hub.py` reconciles Arduino snapshots and tag events.
- `train/modules/automation.py` provides the public `AutomationContext` DSL.
- `train/modules/web_api.py` exposes train, hub, automation, and log endpoints.

Local automation imports `AutomationContext` from `train.automation` and event
classes from `train.domain`, registers event handlers in synchronous
`configure(ctx)`, and performs long-running work in `async run(ctx)`.

Run locally:

```sh
cd backend
python -m venv .venv
. .venv/bin/activate
pip install --index-url https://pypi.org/simple/ -e ".[dev]"
python -m train
pytest tests -q
```

## Operator tools

```sh
tools/train --help
tools/scan-ble
tools/server-push
```

All operational URLs and device choices come from the ignored workspace. Tools
may accept explicit command-line overrides, but tracked files must not contain
installation-specific addresses, IDs, ports, credentials, or automation.

`tools/server-push` produces a content-addressed backend wheel bundle and
publishes it with the configured FTP server. `tools/server-loop` is the stable
server-side supervisor: it verifies releases, atomically switches `current`,
restarts the backend, and rolls back startup failures. The server does not pull
or run repository code through Git.

## Web UI

The frontend is intentionally independent from the backend. Build it as static
files and serve the generated directory with any static host:

```sh
cd web
npm ci
npm run build
```

The generated site is written to `web/out/`; production does not require a
Node.js server.
