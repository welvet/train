import type { StateEnvelope } from "@/src/api/train-api-client";

import type { SystemModel } from "./system";

export function toSystemModel(envelope: StateEnvelope): SystemModel {
  const state = envelope.state;
  return {
    revision: state.revision,
    updatedAt: state.updated_at * 1000,
    running: state.running,
    automationHalted: state.automation.halted,
    trains: Object.values(state.trains)
      .map((train) => {
        const hub = state.lego_hubs[train.lego_hub_id];
        return {
          id: train.train_id,
          speed: train.speed,
          legoHub: hub
            ? {
                id: hub.hub_id,
                connected: hub.connected,
                batteryPct: hub.battery_pct,
                voltage: hub.voltage,
              }
            : null,
        };
      })
      .sort(byId),
    arduinoHubs: Object.values(state.arduino_hubs)
      .map((hub) => ({
        id: hub.hub_id,
        deviceId: hub.device_id,
        connected: hub.connected,
        switches: Object.values(hub.switches)
          .map((item) => ({ id: item.switch_id, angle: item.angle }))
          .sort(byId),
        detectors: Object.values(hub.detectors)
          .map((item) => ({
            id: item.detector_id,
            available: item.available,
            triggered: item.triggered,
            trainId: item.train_id,
            unknownTagId: item.unknown_tag_id,
          }))
          .sort(byId),
      }))
      .sort(byId),
  };
}

function byId<T extends { id: string }>(left: T, right: T): number {
  return left.id.localeCompare(right.id, undefined, { numeric: true });
}
