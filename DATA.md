# Local railway workspace

`data/` contains one railway installation. It is ignored by Git and must not
be used by repository tests or reviews. Back it up separately if needed.

Create or validate a workspace from the repository root:

```sh
tools/data init
tools/data validate
```

Use `TRAIN_DATA_DIR=/another/path` to keep the workspace elsewhere. The
default is `<repository>/data`.

## Files

### `backend.json`

Defines the backend's HTTP API and Arduino TCP listener:

```json
{
  "api": {"host": "0.0.0.0", "port": 8080, "url": "http://127.0.0.1:8080"},
  "arduino_server": {"host": "0.0.0.0", "port": 9000}
}
```

### `trains.json`

Maps stable train IDs to LEGO BLE addresses and NFC tag UIDs:

```json
{
  "trains": [
    {"id": "train_1", "ble_address": "AA:BB:CC:DD:EE:FF", "tag_id": "04:A1:B2:C3"}
  ]
}
```

### `arduinos.json`

Defines any number of named Arduino devices. Each device may have multiple
switches and multiple PN532 readers sharing the hardware SPI bus:

```json
{
  "devices": {
    "arduino_1": {
      "port": "/dev/cu.usbmodem...",
      "fqbn": "arduino:renesas_uno:unor4wifi",
      "baudrate": 9600,
      "hub_id": "hub_1",
      "backend_host": "192.168.1.10",
      "backend_port": 9000,
      "servo_settle_ms": 500,
      "reconnect_ms": 2000,
      "switches": [
        {"id": "S1", "pin": 9, "straight": 58, "diverge": 100}
      ],
      "readers": [
        {"id": "D1", "ss_pin": 4, "read_timeout_ms": 250, "removal_delay_ms": 750}
      ]
    }
  }
}
```

### `secrets.json`

Provides Wi-Fi credentials per Arduino device:

```json
{"devices": {"arduino_1": {"wifi_ssid": "...", "wifi_password": "..."}}}
```

### `automation.py`

Exports a synchronous registration phase and an asynchronous runtime entry
point:

```python
from train.automation import TagDetected


async def on_train_detected(event):
    print(f"Train arrived: {event.train_id}")


def configure(ctx):
    ctx.on(TagDetected, on_train_detected)


async def run(ctx):
    await ctx.forever()
```

`configure` registers handlers before hardware modules start, so startup events
cannot be missed. The script may import `AutomationContext` and supported event
classes from `train.automation`. It is loaded only when the backend starts.

## Commands

```sh
tools/arduino compile arduino_1
tools/arduino upload arduino_1
tools/arduino monitor arduino_1
tools/train --help
tools/scan-ble
tools/commit "commit message"
tools/run-loop
```

`tools/data init` creates an intentionally empty scaffold. Add at least one
train and one Arduino device, then run `tools/data validate`.
