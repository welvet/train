# Repository instructions

The tracked repository is reusable product code. The top-level `data/`
directory is the operator's local railway workspace and is intentionally
excluded from Git.

- Do not search, list, inspect, test, lint, review, stage, or commit anything
  under `data/` unless the user explicitly asks to work with workspace data.
- Never copy values from `data/` into tracked files, logs, test fixtures, PRs,
  or responses. It may contain device identifiers and credentials.
- Tests must create isolated temporary configurations; they must never depend
  on or mutate the real `data/` directory.
- Product code belongs in `backend/`, `firmware/`, and `tools/`. Runtime
  choices—trains, Arduino devices, track automation, and secrets—belong only
  in `data/`.
- `deploy/`, `releases/`, and `current` are server-loop runtime state. They are
  ignored and must never be staged or treated as source.
- See `DATA.md` for the workspace schema and supported commands.
