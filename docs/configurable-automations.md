# Configurable automation design

Status: proposed; this document does not change the current `automation.py`
runtime.

## Goal

Replace installation-written Python automation with a small JSON action tree
that can later be edited by the web UI. A rule starts with one concrete event:
a configured train is detected by a configured detector. The rule then walks
an action tree which can move switches, change the detected train's speed,
wait, or act only on a particular occurrence.

The first version is deliberately small. It is for a LEGO railway, so it does
not try to be a general workflow language or a railway interlocking system.
There are no expressions, variables, loops, priorities, or arbitrary code.

The proposed workspace file is `data/automations.json`. Like the other files
under `data/`, it belongs to one installation and must remain outside Git.

## Complete document

```json
{
  "version": 1,
  "rules": [
    {
      "id": "send_red_train_from_station",
      "enabled": true,
      "trigger": {
        "type": "train_detected",
        "hub_id": "hub_1",
        "detector_id": "station",
        "train_id": "red_train"
      },
      "action": {
        "type": "sequence",
        "actions": [
          {
            "type": "set_switch",
            "hub_id": "hub_1",
            "switch_id": "S1",
            "position": "straight"
          },
          {
            "type": "delay",
            "seconds": 1,
            "action": {
              "type": "set_train_speed",
              "speed": 45
            }
          }
        ]
      }
    }
  ]
}
```

`version` selects the file format. The backend must reject versions it does
not understand instead of guessing. `rules` is an ordered list for stable UI
display; list order does not give a rule priority. An empty `rules` list is
valid and means that no configurable automation is active.

## Rules and triggers

Each rule has these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Stable, unique identifier used by the UI, logs, and runtime state. |
| `enabled` | boolean | Disabled rules neither count detections nor run actions. |
| `trigger` | object | The detector and train pair that starts the rule. |
| `action` | action node | The root of the action tree. |

Version 1 has one trigger type, `train_detected`:

```json
{
  "type": "train_detected",
  "hub_id": "hub_1",
  "detector_id": "D1",
  "train_id": "red_train"
}
```

Detector IDs are scoped to an Arduino hub, so both `hub_id` and `detector_id`
are required. The backend matches this trigger to the existing `TagDetected`
event's `hub_name`, `detector_name`, and `train_id`. A tag which remains on a
detector across a brief hub reconnect does not create another occurrence. An
active tag first discovered in a hub's startup snapshot does create one. The
editor should make that startup behavior visible because starting the backend
with a train already on a detector can immediately actuate the railway.

Only one rule for a particular `(hub_id, detector_id, train_id)` tuple may be
enabled. If several things should happen for the same detection, they belong
in one `sequence`. The UI can keep alternative rules but must disable all but
one of them before saving.

## Action nodes

Every node has a `type` discriminator. Terminal nodes perform a hardware
command. Container nodes own one or more nested nodes, which gives the UI a
simple tree to render and edit.

| Type | Kind | Fields | Behavior |
| --- | --- | --- | --- |
| `set_train_speed` | terminal | `speed` | Sets the train from the trigger to a signed speed from `-100` to `100`. Zero stops it. |
| `set_switch` | terminal | `hub_id`, `switch_id`, `position` | Moves a configured switch to `straight` or `diverge`. |
| `sequence` | container | `actions` | Runs one or more child nodes in order. |
| `delay` | container | `seconds`, `action` | Waits, then runs its child node. |
| `on_count` | conditional container | `count`, `mode`, `action` | Runs its child only when this node reaches the configured occurrence. |

### Set the detected train's speed

```json
{
  "type": "set_train_speed",
  "speed": -35
}
```

The target train is intentionally not configurable on this node: it is always
the train named by the rule trigger. This keeps a detector/train rule local and
prevents an accidental edit from driving an unrelated train.

### Set a switch

```json
{
  "type": "set_switch",
  "hub_id": "hub_1",
  "switch_id": "S2",
  "position": "diverge"
}
```

Version 1 exposes the configured `straight` and `diverge` positions, not raw
servo angles. A successful command means the Arduino accepted the target; the
switch has no physical position sensor.

### Sequence

```json
{
  "type": "sequence",
  "actions": [
    {"type": "set_train_speed", "speed": 0},
    {
      "type": "set_switch",
      "hub_id": "hub_1",
      "switch_id": "S1",
      "position": "straight"
    }
  ]
}
```

Children run in array order. Each hardware command is awaited before the next
child starts. A switch acknowledgement does not mean that the servo has
physically settled. A sequence which will move a train across that switch must
include a suitable `delay` between `set_switch` and `set_train_speed`.

### Delay

```json
{
  "type": "delay",
  "seconds": 5,
  "action": {
    "type": "set_train_speed",
    "speed": 40
  }
}
```

`seconds` is a finite number from `0` through `3600`. The delay is asynchronous,
so hardware connections and the web API continue running while this rule waits.

### Occurrence count

```json
{
  "type": "on_count",
  "count": 5,
  "mode": "once",
  "action": {
    "type": "set_train_speed",
    "speed": 50
  }
}
```

Each time execution reaches an `on_count` node, its private counter advances.
With `mode: "once"`, the child runs only when the counter reaches `count`; the
node remains closed afterward. With `mode: "repeat"`, the child runs on every
multiple of `count`, such as the 5th, 10th, and 15th occurrences. `count` must
be a positive integer. A qualifying occurrence is consumed before its child
runs. If that child later fails or is cancelled, `once` remains closed and
`repeat` waits for the next multiple; an arrival is never relabeled as the
fifth one after the fact.

Counters belong to the node's path within a rule, not just to its displayed
contents. They are runtime state and are not written back to JSON. They reset
when the backend starts, when the rule is disabled and enabled again, or when
that parsed rule definition changes. Formatting-only edits to the file do not
reset counters. Moving or replacing a node does reset its counter, which is
acceptable for this hobby installation.

## Execution model

Each rule is a small state machine:

```text
disabled
   |
   | enable
   v
idle -- matching TagDetected --> running
 ^                              /   |
 |                             /    | delay
 |        action completes ---'     v
 |                               waiting
 |                                  |
 '----------------------------------'
```

When a matching detection arrives in `idle`, the rule evaluates its tree. A
blocked `on_count` returns directly to `idle`; a passing node continues into
its child. Terminal commands use the backend's existing acknowledged
`SetTrainSpeed` and `SetSwitchPosition` command paths.

The event-bus subscriber only matches the trigger, admits the run, updates any
immediate state, and starts an engine-owned task. It then returns without
waiting for the action tree. This is required because event publication awaits
subscribers, while an Arduino connection reads messages serially: awaiting a
switch action inside the subscriber would prevent that same connection from
reading the acknowledgement. The engine tracks every execution task so it can
cancel and await it during reconfiguration, halt, or backend shutdown.

A rule has at most one active execution. Another matching detection while that
rule is `running` or `waiting` is ignored and does not advance counters. This
simple rule prevents two delayed copies of the same action tree from racing.
Different rules may run concurrently.

Disabling a rule cancels its complete execution, including a pending delay or
an awaited command, and prevents any later nodes from running. A command which
was already sent may still have affected the hardware even though its wait was
cancelled. A global automation halt does the same for every rule, but does not
automatically stop trains or move switches. Resuming returns enabled rules to
`idle`; events skipped during the halt are not replayed. Halt and resume keep
occurrence counters; disabling and re-enabling an individual rule resets them.
A future UI should label this control **Pause automation**, not **Stop railway**
or **Emergency stop**.

If a terminal command is rejected, times out, or targets disconnected hardware,
the complete current execution stops, including later actions in every enclosing
sequence. The backend logs the rule ID and failing node. The rule returns to
`idle` for a future detection; it is not permanently disabled by a transient
hardware failure.

## Validation and simple conflict handling

The complete file is validated before it replaces the active configuration.
An invalid edit leaves the previous valid configuration running. For a valid
edit, unchanged rules and their counters stay alive. The engine first cancels
and awaits executions for changed, removed, or newly disabled rules, resets
their runtime state, and only then publishes the complete new configuration.
Trigger admission is paused for this replacement; detections received during
the short replacement window are not replayed. This prevents a run of the old
tree from starting while its replacement is being installed, and prevents an
old delayed tree from acting after the UI displays the replacement.

Validation checks that:

- rule IDs are non-empty and unique;
- every train, hub, detector, and switch exists in `trains.json` or
  `arduinos.json`, and every train used by a trigger has an NFC `tag_id`;
- only one rule per detector/train tuple is enabled;
- node fields and values follow the constraints above;
- every sequence has at least one child; and
- unknown versions, node types, fields, and enum values are rejected.

Version 1 does not calculate dependencies or resolve conflicts between
different triggers. Two rules can still target the same train or switch at
about the same time. The existing command bus serializes commands for one
resource, and the last command to run determines its state. The editor should
show a warning for shared targets and let the operator disable one of the
rules. There are no priorities, locks spanning an action tree, or automatic
winner selection.

## Nested example: every fifth arrival

This rule does nothing for the first four accepted detections. On the fifth
accepted detection, it diverts the switch, waits five seconds, then starts the
detected train. It repeats on the tenth accepted detection because the count
mode is `repeat`.

```json
{
  "id": "occasional_station_departure",
  "enabled": true,
  "trigger": {
    "type": "train_detected",
    "hub_id": "hub_1",
    "detector_id": "station",
    "train_id": "red_train"
  },
  "action": {
    "type": "on_count",
    "count": 5,
    "mode": "repeat",
    "action": {
      "type": "sequence",
      "actions": [
        {
          "type": "set_switch",
          "hub_id": "hub_1",
          "switch_id": "S2",
          "position": "diverge"
        },
        {
          "type": "delay",
          "seconds": 5,
          "action": {
            "type": "set_train_speed",
            "speed": 40
          }
        }
      ]
    }
  }
}
```

## Implementation boundary

This proposal replaces the public programmable automation surface; it does not
run alongside user-written `automation.py`. A later implementation should:

1. load and validate `data/automations.json` against the installation topology;
2. translate `TagDetected` events into rule invocations;
3. keep rule state, timers, and counters inside one internal automation engine;
4. dispatch the existing acknowledged train and switch commands; and
5. expose validated rule configuration and runtime status for a future UI.

Arbitrary event subscriptions, Python callbacks, speed ramps, and custom
background tasks are intentionally outside version 1. New trigger or node
types can be added in a later schema version when there is a concrete UI use
case.
