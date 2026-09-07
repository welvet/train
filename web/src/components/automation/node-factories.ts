import type { AutomationNode, SwitchOption } from "./types";

export type AutomationNodeType = Exclude<AutomationNode["type"], "branch">;

export function createNode(
  type: AutomationNodeType,
  switches: readonly SwitchOption[],
  signals: readonly string[],
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
        children: [],
      };
    case "on_count":
      return {
        type,
        count: 2,
        children: [],
      };
    case "if_count":
      return {
        type,
        count: 5,
        children: [
          { type: "branch", when: "match", children: [] },
          { type: "branch", when: "otherwise", children: [] },
        ],
      };
    case "set_signal":
      return { type, signal: signals[0] ?? "", value: 1, children: [] };
    case "on_signal":
    case "when_signal_is":
      return {
        type,
        signal: signals[0] ?? "",
        operator: "eq",
        value: 1,
        children: [],
      };
    case "if_signal":
      return {
        type,
        signal: signals[0] ?? "",
        operator: "eq",
        value: 1,
        children: [
          { type: "branch", when: "match", children: [] },
          { type: "branch", when: "otherwise", children: [] },
        ],
      };
  }
}
