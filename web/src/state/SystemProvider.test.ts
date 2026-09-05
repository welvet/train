import type { StateEnvelope } from "@/src/api/train-api-client";
import { latestState } from "./SystemProvider";

it("rejects snapshots with an older snapshot timestamp", () => {
  const current = stateEnvelope(7, 200);

  expect(latestState(current, stateEnvelope(8, 199))).toBe(current);
});

it("accepts a newer timestamp after a backend revision reset", () => {
  const restarted = stateEnvelope(0, 201);

  expect(latestState(stateEnvelope(7, 200), restarted)).toBe(restarted);
});

it("uses the revision to order snapshots with the same timestamp", () => {
  const current = stateEnvelope(7, 200);
  const older = stateEnvelope(6, 200);
  const newer = stateEnvelope(8, 200);

  expect(latestState(current, older)).toBe(current);
  expect(latestState(current, newer)).toBe(newer);
});

function stateEnvelope(revision: number, snapshotAt: number): StateEnvelope {
  return {
    version: 4,
    snapshot_at: snapshotAt,
    automation: {
      document: { version: 1, rules: [] },
      eligible_train_ids: [],
      paused: false,
      statuses: [],
    },
    state: {
      revision,
      updated_at: snapshotAt,
      running: true,
      automation: { halted: false },
      trains: {},
      lego_hubs: {},
      arduino_hubs: {},
    },
  };
}
