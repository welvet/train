# Configurable automations

## Goal

Replace installation-written Python automation with a small JSON state tree
that can later be edited by the web UI. A rule starts with one concrete event:
a configured train is detected by a configured detector. That detector is the
root node. Control nodes below it can wait or act only on a particular
occurrence, while terminal leaves move switches or change the detected train's
speed.

The first version is deliberately small. It is for a LEGO railway, so it does
not try to be a general workflow language or a railway interlocking system.
There are no expressions, variables, loops, priorities, or arbitrary code.

The workspace file is `data/automations.json`. Like the other files
under `data/`, it belongs to one installation and must remain outside Git.

## Complete document

```json
{
  "version": 3,
  "rules": [
    {
      "id": "send_red_train_from_station",
      "enabled": true,
      "root": {
        "type": "train_detected",
        "hub_id": "hub_1",
        "detector_id": "station",
        "train_id": "red_train",
        "children": [
          {
            "type": "set_switch",
            "hub_id": "hub_1",
            "switch_id": "S1",
            "position": "straight",
            "children": []
          },
          {
            "type": "wait",
            "seconds": 1,
            "children": [
              {
                "type": "set_train_speed",
                "speed": 45,
                "children": []
              }
            ]
          }
        ]
      }
    }
  ]
}
```

`version` selects the file format and execution contract. Version 1 contains
the original linear and filtering nodes with ordered children. Version 2 adds
exclusive count branching while retaining version 1 behavior. Version 3 starts
every entered sibling set concurrently at every tree depth. The current backend
can read versions 1 and 2 only as migration input: it validates and atomically
persists the same tree as version 3 before activation. API replacements follow
the same rule, and the editor always saves version 3. The standalone runner
executes only version 3.

Rolling back to a version-1-or-2-only backend therefore fails closed until an
operator deliberately changes the document version and accepts the old ordered
semantics. Unsupported versions are rejected instead of guessed.
`rules` is an ordered list for stable UI
display; list order does not give a rule priority. An empty `rules` list is
valid and means that no configurable automation is active.

## Rules and triggers

Each rule has these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Stable, unique identifier used by the UI, logs, and runtime state. |
| `enabled` | boolean | Disabled rules neither count detections nor run actions. |
| `root` | `train_detected` node | The detector and train pair that starts the tree. |

All current document versions have one root type, `train_detected`:

```json
{
  "type": "train_detected",
  "hub_id": "hub_1",
  "detector_id": "D1",
  "train_id": "red_train",
  "children": [
    {
      "type": "set_train_speed",
      "speed": 40,
      "children": []
    }
  ]
}
```

Detector IDs are scoped to an Arduino hub, so both `hub_id` and `detector_id`
are required. The backend matches this root to the existing `TagDetected`
event's `hub_name`, `detector_name`, and `train_id`. A tag which remains on a
detector across a brief hub reconnect does not create another occurrence. An
active tag first discovered in a hub's startup snapshot does create one. The
editor should make that startup behavior visible because starting the backend
with a train already on a detector can immediately actuate the railway.

Only one rule for a particular `(hub_id, detector_id, train_id)` tuple may be
enabled. The UI can keep alternative rules but must disable all but one of them
before saving.

## Tree nodes

Every node has a `type` discriminator and a `children` array, so the UI can
render and edit the complete structure with one recursive tree component.
In version 3, children start concurrently; array order is structural and keeps
node paths, counters, errors, branch identity, and editor display stable. It is
not execution order. Control nodes own one or more children; terminal hardware
nodes are leaves and require an empty `children` array.

| Type | Kind | Fields | Behavior |
| --- | --- | --- | --- |
| `train_detected` | root | `hub_id`, `detector_id`, `train_id`, `children` | Runs its children when the configured detector sees the configured train. |
| `set_train_speed` | terminal | `speed`, `children` | Sets the train from the root to a signed speed from `-100` to `100`. Zero stops it. |
| `set_switch` | terminal | `hub_id`, `switch_id`, `position`, `children` | Moves a configured switch to `straight` or `diverge`, or `flip`s its last-known position. |
| `wait` | control | `seconds`, `children` | Waits, then starts all of its children concurrently. |
| `on_count` | conditional | `count`, `children` | Runs its children on every configured occurrence. |
| `if_count` | conditional, v2+ | `count`, `children` | Selects its `match` branch on every configured occurrence and `otherwise` on the rest. |
| `branch` | control, v2+ | `when`, `children` | Labels the `match` or `otherwise` subtree directly beneath `if_count`. |

### Set the detected train's speed

```json
{
  "type": "set_train_speed",
  "speed": -35,
  "children": []
}
```

The target train is intentionally not configurable on this node: it is always
the train named by the rule root. This keeps a detector/train rule local and
prevents an accidental edit from driving an unrelated train.

### Set a switch

```json
{
  "type": "set_switch",
  "hub_id": "hub_1",
  "switch_id": "S2",
  "position": "diverge",
  "children": []
}
```

The automation format exposes the configured `straight`, `diverge`, and `flip`
positions, not raw servo angles. `flip` resolves from the last position
acknowledged by the Arduino. If that position is unknown or is not one of the
two configured endpoints, automation assumes it was straight and moves it to
diverge. This option belongs to the automation document; the public
manual-control event continues to accept explicit positions and raw angles only.

A successful command means the Arduino accepted the target; the switch has no
physical position sensor. In version 3, sibling commands and waits start
together. A delayed action must be nested under its `wait`; for example, a
`set_switch` sibling and a `wait` containing `set_train_speed` begin together,
then the speed command begins when that wait expires. The current vocabulary
cannot express "start the timer only after switch acknowledgement"; that would
require an explicit sequencing control node.

### Wait

```json
{
  "type": "wait",
  "seconds": 5,
  "children": [
    {
      "type": "set_train_speed",
      "speed": 40,
      "children": []
    }
  ]
}
```

`seconds` is a finite number from `0` through `3600`. The wait is asynchronous,
so hardware connections and the web API continue running while this rule waits.

### Occurrence count

```json
{
  "type": "on_count",
  "count": 5,
  "children": [
    {
      "type": "set_train_speed",
      "speed": 50,
      "children": []
    }
  ]
}
```

Each time execution reaches an `on_count` node, its private counter advances.
Its children run on every multiple of `count`, such as the 5th, 10th, and 15th
occurrences. `count` must be a positive integer. A qualifying occurrence is
consumed before its children run. If a child later fails or is cancelled, the
node waits for the next multiple; an arrival is never relabeled as the fifth
one after the fact.

Counters belong to the node's path within a rule, not just to its displayed
contents. They are runtime state and are not written back to JSON. They reset
when the backend starts or a complete document is applied through the API.

### Count branch (introduced in version 2)

Use `if_count` when both the matching and non-matching occurrences need an
action. It requires exactly one `match` branch and one `otherwise` branch, and
executes exactly one of them each time execution reaches the node. Branch order
in JSON does not change their meaning.

For example, this keeps a switch straight for four passes and sends the fifth
pass down the diverging route, repeating the cycle on the 10th, 15th, and later
multiples:

```json
{
  "type": "if_count",
  "count": 5,
  "children": [
    {
      "type": "branch",
      "when": "match",
      "children": [
        {
          "type": "set_switch",
          "hub_id": "hub_1",
          "switch_id": "S1",
          "position": "diverge",
          "children": []
        }
      ]
    },
    {
      "type": "branch",
      "when": "otherwise",
      "children": [
        {
          "type": "set_switch",
          "hub_id": "hub_1",
          "switch_id": "S1",
          "position": "straight",
          "children": []
        }
      ]
    }
  ]
}
```

The counter advances whenever traversal reaches this particular node. At the
root level that is every admitted matching detection. A nested `if_count` only
counts executions that reach it. As with `on_count`, a failed or cancelled
branch does not roll the occurrence back.

Switch acknowledgement means the Arduino accepted the command, not that a
physical position sensor observed completion. Place the detector far enough
before the switch for it to settle before the train arrives.

## Execution model

Each rule is a small state machine:

```text
disabled
   |
   | enable
   v
idle -- matching TagDetected --> running
 ^                              /   |
 |                             /    | wait
 |          tree completes ---'     v
 |                               waiting
 |                                  |
 '----------------------------------'
```

When a matching detection arrives in `idle`, the rule enters its root and
starts every root child concurrently. The same rule applies recursively to
every child set. A blocked `on_count` skips its subtree and returns to its
parent; a passing node starts its children together. An `if_count` selects only
one branch, whose children then start together. A `wait` sleeps before starting
its own children, without delaying sibling paths. Terminal commands use the
backend's existing acknowledged
`SetTrainSpeed` and `SetSwitchPosition` command paths.

The event-bus subscriber only matches the root condition, admits the run,
updates any immediate state, and starts an engine-owned task. It then returns
without waiting for the state tree. This is required because event publication
awaits subscribers, while an Arduino connection reads messages serially:
awaiting a switch command inside the subscriber would prevent that same
connection from reading the acknowledgement. The engine tracks every execution
task so it can cancel and await it during reconfiguration, halt, or backend
shutdown.

A rule has at most one active execution. Another matching detection while that
rule is `running` or `waiting` is ignored and does not advance counters. This
simple rule prevents two delayed copies of the same state tree from racing.
Different rules may run concurrently. A rule reports `waiting` whenever at
least one of its active paths is sleeping, even if another path is running a
command at the same time.

Disabling a rule cancels its complete execution, including a pending wait or
an awaited command, and prevents any later nodes from running. A command which
was already sent may still have affected the hardware even though its wait was
cancelled. A global automation halt does the same for every rule, but does not
automatically stop trains or move switches. Resuming returns enabled rules to
`idle`; events skipped during the halt are not replayed. Halt and resume keep
occurrence counters; disabling and re-enabling an individual rule resets them.
A future UI should label this control **Pause automation**, not **Stop railway**
or **Emergency stop**.

If a terminal command is rejected, times out, or targets disconnected hardware,
unfinished sibling paths are cancelled and awaited. Every sibling in the cohort
has already started, and a hardware command already sent may still affect the
railway even if its awaiting task is cancelled. The backend reports one failing
node deterministically by array order when failures race. The rule returns to
`idle` for a future detection; it is not permanently disabled by a transient
hardware failure.

## Validation and simple conflict handling

The complete file is validated before it replaces the active configuration.
An invalid edit leaves the previous valid configuration running. For every
valid API update, the engine cancels and awaits all current executions, resets
all runtime counters, and only then publishes the complete new configuration.
Trigger admission is paused for this replacement; detections received during
the short replacement window are not replayed. This prevents a run of the old
tree from starting while its replacement is being installed, and prevents an
old delayed tree from acting after the UI displays the replacement.

Validation checks that:

- rule IDs are non-empty and unique;
- every train, hub, detector, and switch exists in `trains.json` or
  `arduinos.json`, and every train used by a root has at least one configured
  NFC tag UID;
- only one rule per detector/train tuple is enabled;
- node fields and values follow the constraints above;
- every rule has exactly one `train_detected` root, and `train_detected` does
  not appear below that root;
- every node contains a `children` array, roots and control nodes have at least
  one child, and terminal nodes have none;
- unknown versions, node types, fields, and enum values are rejected.

Version 3 does not calculate dependencies or resolve target conflicts. Sibling
paths in one rule, or paths in different rules, can target the same train or
switch at about the same time. The existing command bus serializes commands for
one resource but does not promise which concurrent command acquires its lock
first, so the final state is unspecified. After a timeout, the physical outcome
also remains unknown. The editor warns about shared targets across rules and
about concurrent same-target paths within one rule; mutually exclusive
`if_count` branches do not conflict with each other. The operator can change or
disable a conflicting path. There are no priorities, locks spanning a state
tree, or automatic winner selection.

## Nested example: every fifth arrival

This rule does nothing for the first four accepted detections. On the fifth it
sets speed to `50` after five seconds, stops after ten seconds, and sets speed
to `20` after fifteen seconds. The schedule repeats on every fifth accepted
detection.

```json
{
  "id": "occasional_station_departure",
  "enabled": true,
  "root": {
    "type": "train_detected",
    "hub_id": "hub_1",
    "detector_id": "station",
    "train_id": "red_train",
    "children": [
      {
        "type": "on_count",
        "count": 5,
        "children": [
          {
            "type": "wait",
            "seconds": 5,
            "children": [
              {
                "type": "set_train_speed",
                "speed": 50,
                "children": []
              },
              {
                "type": "wait",
                "seconds": 5,
                "children": [
                  {
                    "type": "set_train_speed",
                    "speed": 0,
                    "children": []
                  },
                  {
                    "type": "wait",
                    "seconds": 5,
                    "children": [
                      {
                        "type": "set_train_speed",
                        "speed": 20,
                        "children": []
                      }
                    ]
                  }
                ]
              }
            ]
          }
        ]
      }
    ]
  }
}
```

## Implementation boundary

This runtime replaces the old programmable automation surface; it does not run
installation-written Python. The backend:

1. loads and validates `data/automations.json` against the installation topology;
2. translates `TagDetected` events into root-node invocations;
3. keeps rule state, timers, and counters inside one internal automation engine;
4. dispatches the existing acknowledged train and switch commands; and
5. exposes validated rule configuration and runtime status through the web API.

Arbitrary event subscriptions, Python callbacks, speed ramps, and custom
background tasks remain outside versions 1 through 3. Further root or node types
require a later schema version and a concrete UI use case.
