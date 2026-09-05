# Web API

The web API is a transport for the backend domain model. It exposes one
authoritative state snapshot and accepts the command events explicitly registered
in `train.domain.vocabulary`. The HTTP layer contains no train-, hub-, or
switch-specific routing.

## Read system state

`GET /api/state` returns the current `SystemState` in a versioned JSON envelope.
Version 3 has the shape
`{"version": 3, "snapshot_at": 123.4, "state": {...}, "automation": {...}}`.
`snapshot_at` records
when the backend created the response so clients can reject older snapshots.
Configured trains, Arduino hubs, switches, and detectors are present before their
hardware connects. Runtime events update the same state read by automation and
the API.

`automation.document` contains the complete JSON stored in
`data/automations.json`. `automation.statuses` reports each rule's current
runtime state and last failure, and `automation.paused` reports the global halt
state. `PUT /api/automation` accepts a complete replacement document. The
backend validates the whole tree and its topology references before atomically
persisting and applying it. Invalid updates leave the previous automation
running. Every valid replacement cancels and awaits all current automation work
and resets occurrence counters before the new tree becomes active.

Server deployments persist the editable document outside immutable release
directories, so updates survive supervisor restarts and later releases.

The top-level `revision` increases whenever an event changes state. `updated_at`
is the timestamp of that event. A response includes:

- backend lifecycle and automation state;
- trains and their linked LEGO hub connection, battery, voltage, and speed
  state; and
- Arduino hubs with their configured device IDs, switches, and detectors.

Hardware addresses, configured train-tag UIDs, pins, and workspace credentials
are not returned. When a detector sees an unconfigured tag, its normalized UID
is included temporarily as `unknown_tag_id` so an operator can identify and add
the train. The UID is cleared when that tag is removed.

`GET /api/state/stream` sends the same complete envelope as a server-sent event
immediately after connection and whenever the state revision changes. Clients
can replace their local snapshot directly; the web client reconnects and
refreshes the snapshot automatically if the stream is interrupted.

## Publish a command event

`POST /api/events` accepts an event envelope:

```json
{
  "type": "set_train_speed",
  "data": {
    "train_id": "express",
    "speed": 50
  }
}
```

Supported event types are `set_train_speed`, `set_switch_position`,
`automation_halt`, and `automation_resume`. Stable public names and validation
live in `train.domain.vocabulary`; adding a public command does not require a new
HTTP route.

The endpoint uses the shared command dispatcher and returns HTTP 200 only after
successful hardware acknowledgement, or after a non-hardware control event has
been applied. It returns 404 when the configured train, Arduino hub, or switch
does not exist, 409 when hardware rejects a command, and 504 when the bounded
command deadline expires. The deadline includes time spent waiting behind
another command for the same resource. Because a 504 does not distinguish a
queued command from one already sent to hardware, inspect current state before
retrying. Commands targeting the same train or switch are serialized across
both automation and HTTP callers.

Version 3 does not accept client idempotency keys. A timeout covers queueing,
publication, and acknowledgement, and means the physical outcome may be unknown.
Inspect state before deciding whether to issue another command.

Events that report facts, such as connections, telemetry, detections, and
hardware acknowledgements, are internal-only and are rejected by this endpoint.

## Generated contract

`GET /api/openapi.json` returns the versioned OpenAPI 3.1 contract for the state
snapshot and public command vocabulary. The checked-in frontend contract is
generated from the backend domain and vocabulary with
`tools/generate-web-contract`; it must not be edited by hand.

## Operational health

`GET /health` remains separate because the release supervisor uses it for
readiness and deployment verification.

## Network boundary

This API intentionally has no authentication. It is for the trusted local
network hosting the LEGO railway and must not be exposed to the internet or an
untrusted network.
