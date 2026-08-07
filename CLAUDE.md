# LEGO Train Automation

Arduino + Python system for controlling a LEGO model train with TrixBrix switch motors and sensors.

## Project structure

- `TrainController/` — Arduino firmware (WiFi, sensors, motor control)
- `backend/` — Python backend (control logic, web API, event bus)
- `ard` — CLI wrapper around `arduino-cli`
- `arduino.json` — Arduino CLI config (port, FQBN, baud rate)

## Arduino (`TrainController/`)

### Board

- **Board**: Arduino UNO R4 WiFi
- **FQBN**: `arduino:renesas_uno:unor4wifi`
- **WiFi library**: `WiFiS3.h`

### Files

- `TrainController.ino` — main sketch; generic controller logic, reads all config from `config.h`
- `config.h` — board identity, device wiring, backend address. One per board variant.
- `secrets.h` — WiFi credentials (`WIFI_SSID`, `WIFI_PASS`). Do not commit.

### CLI (`./ard`)

Wraps `arduino-cli` and reads settings from `arduino.json`.

```
./ard compile     # compile the sketch
./ard upload      # upload to board
./ard go          # compile + upload
./ard monitor     # open serial monitor
./ard boards      # list connected boards
```

Sketch is auto-detected. Override with `--sketch`, `--port`, or `--baudrate`.

### Config (`config.h`)

Defines board identity and all connected devices. The `.ino` is generic and never hardcodes pins or counts.

```c
#define HUB_NAME "A_HUB_1"

// Switches: {name, pin, angleStraight, angleDiverge}
const SwitchConfig SWITCHES[] = { {"S1", 9, 58, 100}, {"S2", 10, 58, 100} };

// Detectors: {name, pin, activeLow}
const DetectorConfig DETECTORS[] = { {"D1", 2, true}, {"D2", 3, true} };

// Backend TCP server
#define BACKEND_HOST "192.168.50.186"
#define BACKEND_PORT 9000
```

To add a new board: duplicate `config.h`, change values. The `.ino` doesn't change.

### TCP protocol

Board connects to backend as a TCP client. Newline-delimited JSON both ways.

**Board → Backend:**
- `{"event":"hello","hub":"A_HUB_1","switches":["S1","S2"],"detectors":["D1","D2"]}` — on connect
- `{"event":"detector","hub":"A_HUB_1","name":"D1","triggered":true}` — on state change
- `{"event":"move_ack","hub":"A_HUB_1","switch":"S1","angle":100,"ok":true}` — after move
- `{"event":"pong","hub":"A_HUB_1"}` — reply to ping

**Backend → Board:**
- `{"cmd":"move","switch":"S1","angle":100}` — move a switch
- `{"cmd":"ping"}` — health check

Board reconnects every 2s if connection drops. Detector events are silently dropped when disconnected.

### LED states

- **Fast blink** — no backend connection (or WiFi connecting)
- **Off** — connected

### Servo behavior

Servos use attach/move/detach pattern — attached only during a throw (500ms settle), then detached to eliminate buzz. Multiple servos can move simultaneously (2A+ USB charger + 1000µF cap handles the combined draw).

### Arduino workflow

```
./ard go          # build and flash
./ard monitor     # watch serial output (Ctrl-C to exit)
```

## Backend (`backend/`)

Python 3.11+ asyncio application. Runtime deps: `bleak` (BLE), `aiohttp` (HTTP).

### Architecture

- `train/core/event_bus.py` — typed pub/sub event bus; subscribe by event class, `isinstance`-based dispatch
- `train/core/events/` — event definitions (frozen dataclasses)
  - `base.py` — `Event` base class
  - `system.py` — `SystemStarted`, `SystemShutdown`
  - `train.py` — `SetTrainSpeed`, `TrainSpeedChanged`, `TrainConnected`, `TrainDisconnected`, `TrainStatus`
  - `hub.py` — `SetSwitchPosition`, `SwitchPositionChanged`, `HubConnected`, `HubDisconnected`, `DetectorChanged`
- `train/core/module.py` — `Module` ABC with `start()`/`stop()` lifecycle
- `train/core/app.py` — `App` orchestrator; registers modules with `**kwargs`, handles SIGINT/SIGTERM, starts/stops in order

### Modules

- `train/modules/lego_ble.py` — LEGO Powered Up BLE connector. Uses `bleak` + LWP3 protocol directly. Manages per-train connection loops with auto-reconnect. Subscribes to `SetTrainSpeed`, publishes `TrainSpeedChanged`, `TrainConnected`, `TrainDisconnected`, `TrainStatus`. Motor command uses StartPower (sub-command `0x51`) on port `0x01`.
- `train/modules/arduino_hub.py` — TCP server for Arduino hubs. Accepts connections on `:9000`. Handles `hello`/`detector`/`move_ack`/`pong` messages. Subscribes to `SetSwitchPosition`, publishes `HubConnected`, `HubDisconnected`, `DetectorChanged`, `SwitchPositionChanged`.
- `train/modules/web_api.py` — REST API via `aiohttp`. Listens on `:8080`. Maintains in-memory state cache built from events.
- `train/modules/automation.py` — Automation DSL module. Provides `AutomationContext` with `set_speed()`, `set_switch()`, `wait_for()`, `on()`, `ramp_speed()`, `spawn()`. Runs a script function as an async task.

### Automation scripts

- `train/scripts/demo_script.py` — demo: sets switches straight on hub connect, starts train on BLE connect, stops on detector, toggles switches on D1.

### LEGO BLE protocol notes

- Hub Service UUID: `00001623-1212-efde-1623-785feabcd123`
- Hub Characteristic UUID: `00001624-1212-efde-1623-785feabcd123`
- Motor is on port `0x01` (Port B). Uses StartPower sub-command `0x51`, not StartSpeed `0x07`.
- Battery: Hub Property `0x06`, request with operation `0x05`, enable updates with `0x02`
- Voltage: Port `0x3C`, subscribe via Port Input Format Setup (`0x41`)

### REST API

- `POST /trains/{train_name}/speed` — body: `{"speed": <-100..100>}`. Returns `{"train_name", "speed", "success"}`. Times out at 2s → 504.
- `GET /trains/{train_name}` — returns `{"train_name", "connected", "speed", "battery_pct", "voltage"}`. 404 if train not seen.
- `GET /hubs/{hub_name}` — returns `{"hub_name", "connected", "switches": [...], "detectors": [...]}`. 404 if hub not seen.
- `POST /hubs/{hub_name}/switches/{switch_name}/position` — body: `{"angle": <int>}`. Returns `{"hub_name", "switch_name", "angle", "ok"}`. Times out at 2s → 504.

### Train config

Trains are mapped by BLE address in `train/__main__.py`:

```python
app.add_module(LegoBleModule, train_map={
    "FB81D51D-F808-C900-5C30-00076EBA9465": "arctic_express",
})
```

### Scripts

- `scripts/scan_ble.py` — scan for nearby LEGO Powered Up hubs
- `scripts/hub_info.py` — connect to hub, show attached devices and ports
- `scripts/test_motor.py` — try different motor commands to find working port/sub-command
- `scripts/test_battery.py` — test battery and voltage reading

### Backend workflow

```
cd backend
python -m venv .venv && source .venv/bin/activate
pip install --index-url https://pypi.org/simple/ -e ".[dev]"
python -m train            # run (Ctrl-C to stop)
pytest tests/ -v           # run tests
```

Note: pip defaults to Spotify's internal artifactory which may be unreachable. Use `--index-url https://pypi.org/simple/` to install from public PyPI.
