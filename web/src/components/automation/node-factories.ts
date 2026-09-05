import type { AutomationNode, SwitchOption } from "./types";

export type AutomationNodeType = AutomationNode["type"];

export function createNode(
  type: AutomationNodeType,
  switches: readonly SwitchOption[],
): AutomationNode {
  switch (type) {
    case "set_train_speed":
      return { type, speed: 0, children: [] };
    case "set_switch": {
      const first = switches[0];
      return {
        type,
        hub_id: first?.hubId ?? "",
        switch_id: first?.switchId ?? "",
        position: "straight",
        children: [],
      };
    }
    case "wait":
      return {
        type,
        seconds: 1,
        children: [{ type: "set_train_speed", speed: 0, children: [] }],
      };
    case "on_count":
      return {
        type,
        count: 2,
        mode: "once",
        children: [{ type: "set_train_speed", speed: 0, children: [] }],
      };
  }
}
