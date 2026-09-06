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

The HTTP API can actuate the railway and intentionally has no authentication.
Bind or expose it only on the trusted local network; never publish it to the
internet or an untrusted network.

### `trains.json`

Maps stable train IDs to LEGO BLE addresses and NFC tag UIDs:

```json
{
  "trains": [
    {
      "id": "train_1",
      "lego_hub_id": "hub_red",
      "ble_address": "AA:BB:CC:DD:EE:FF",
      "tag_ids": ["04:A1:B2:C3", "04:D4:E5:F6"]
    }
  ]
}
```

`lego_hub_id` is the stable identity of the physical LEGO hub paired with the
train. It defaults to the train `id` when omitted, so existing workspaces remain
valid. `tag_ids` lists every NFC tag attached to the same physical train. Tag
UIDs must be unique across the whole workspace. The legacy singular `tag_id`
field remains accepted as a single-item list, but a train must not define both
fields.

Upload firmware built from this version before relying on multiple tags for one
train. Older firmware remains protocol-compatible, but may report a direct
change between two tags as a removal followed by a new detection; updated
firmware lets the backend coalesce both tags into one continuous train presence.

The complete train document is available through `GET /api/configuration` and
can be replaced atomically with `PUT /api/configuration`. The API uses a
versioned `documents` envelope so more editable workspace files can be added
without creating a separate top-level protocol. Updates are validated and
written to `trains.json`; restart the backend before expecting the new topology
to control hardware.

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
      "event_logger_enabled": true,
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

`read_timeout_ms` may be at most 1000 ms so NFC polling cannot block heartbeat
responses long enough for the backend to disconnect a healthy Arduino hub.

`event_logger_enabled` is optional and defaults to `false`. When enabled, the
firmware prints one line for every internal event to the Arduino serial output.

### `secrets.json`

Provides Wi-Fi credentials per Arduino device and the FTP deployment password:

```json
{
  "devices": {
    "arduino_1": {"wifi_ssid": "...", "wifi_password": "..."}
  },
  "deployment": {"ftp_password": "..."}
}
```

### `deployment.json`

Defines where `tools/server-push` publishes backend releases:

```json
{
  "ftp": {
    "host": "192.168.1.10",
    "port": 2121,
    "username": "operator",
    "remote_dir": "/train/deploy",
    "tls": false
  },
  "health_url": "http://192.168.1.10:8080",
  "target": {
    "system": "Darwin",
    "machine": "arm64",
    "implementation": "cpython",
    "python": "3.14",
    "platform": "macosx-26.0-arm64",
    "soabi": "cpython-314-darwin"
  }
}
```

The password is deliberately separate from this file. Set `tls` when the server
supports explicit FTPS. Certificate verification uses the system trust store;
set `ftp.ca_file` to a local CA bundle for a private certificate authority.
Plain FTP is an explicitly trusted-LAN mode because it does not encrypt
credentials or release contents.

The target fields are the server's exact deployment contract. The backend is a
pure Python wheel, so `server-push` can build on a newer macOS host while pip
selects binary dependencies for the configured server platform, Python, and
ABI. Runtime dependencies are pinned with hashes in a target-keyed file under
`backend/requirements/`. `tools/data init` leaves the target empty because it
is an installation choice; copy these values from the server's Python runtime.

### `automations.json`

Stores the versioned configurable automation tree:

```json
{
  "version": 1,
  "rules": []
}
```

The backend validates node structure and all train, hub, detector, and switch
references at startup. The complete document is returned in `GET /api/state`
and can be replaced with `PUT /api/automation`. See
[Configurable automations](docs/configurable-automations.md) for the format and
runtime semantics.

On the deployment server, the supervisor seeds this file once into the
persistent `<server-root>/data/` directory. API edits therefore survive backend
restarts and later content-addressed releases; immutable release data is never
modified.

## Commands

```sh
tools/arduino compile arduino_1
tools/arduino upload arduino_1
tools/arduino monitor arduino_1
tools/scan-ble
tools/server-push
```

`tools/data init` creates an intentionally empty scaffold. Add at least one
train and one Arduino device, then run `tools/data validate`.

## Server deployment

`tools/server-push` builds the static frontend first, packages it with the
backend and all Python dependencies into a wheel bundle, and adds only the
runtime data files. Wi-Fi and FTP secrets are never
included. The release is uploaded under its SHA-256 name, and `release.json`
with a unique publication attempt is updated last to trigger activation. The
command returns only after both the FTP activation marker and the backend's
release-aware health endpoint agree.

Before building, `server-push` synchronizes `trains.json` with the running
backend. If the documents differ, the file with the newer modification
timestamp replaces the older one; equal contents need no copy. Keep the
deployment machine and server clocks synchronized. A backend without the
configuration endpoint is treated as a bootstrap deployment and uses the local
file. On the server, editable trains are stored in persistent
`<server-root>/data/trains.json`, outside immutable release directories.

Bootstrap the permanent watcher once on the server from the FTP root:

```sh
python3 /train/deploy/server-loop --root /train
```

`server-push` uploads this bootstrap script alongside every release. Run it
under the server's process supervisor so it survives logout and reboot. The FTP
`remote_dir` must map to `<server root>/deploy`; for the example above that is
`/train/deploy`. The loop verifies and prepares each release in `releases/`,
starts the candidate before atomically updating `current`, and writes supervisor,
backend, dependency-install, and status logs under `deploy/`. A release that fails readiness is
rolled back, and only the three newest healthy/rollback releases are retained.
