import type { StateEnvelope } from "@/src/api/train-api-client";

import { toSystemModel } from "./system-mapper";

it("maps and sorts the backend state into the UI model", () => {
  const envelope: StateEnvelope = {
    version: 1,
    snapshot_at: 13,
    state: {
      revision: 7,
      updated_at: 12.5,
      running: true,
      automation: { halted: false },
      trains: {
        zed: { train_id: "zed", lego_hub_id: "hub-z", speed: -20 },
        alpha: { train_id: "alpha", lego_hub_id: "hub-a", speed: 30 },
      },
      lego_hubs: {
        "hub-z": {
          hub_id: "hub-z",
          train_id: "zed",
          connected: false,
          battery_pct: 0,
          voltage: 0,
        },
        "hub-a": {
          hub_id: "hub-a",
          train_id: "alpha",
          connected: true,
          battery_pct: 72,
          voltage: 7.4,
        },
      },
      arduino_hubs: {
        yard: {
          hub_id: "yard",
          device_id: "arduino-1",
          connected: true,
          switches: { S2: { switch_id: "S2", angle: 90 } },
          detectors: {
            D1: {
              detector_id: "D1",
              available: true,
              triggered: true,
              train_id: "alpha",
            },
          },
        },
      },
    },
  };

  const model = toSystemModel(envelope);

  expect(model.updatedAt).toBe(12_500);
  expect(model.trains.map((train) => train.id)).toEqual(["alpha", "zed"]);
  expect(model.trains[0].legoHub).toMatchObject({
    id: "hub-a",
    connected: true,
    batteryPct: 72,
  });
  expect(model.arduinoHubs[0].detectors[0]).toMatchObject({
    id: "D1",
    triggered: true,
    trainId: "alpha",
  });
});
