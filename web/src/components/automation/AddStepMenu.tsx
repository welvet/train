import { Button, Menu } from "@mantine/core";

import type { AutomationNodeType } from "./node-factories";

const STEP_TYPES: readonly {
  type: AutomationNodeType;
  label: string;
  description: string;
}[] = [
  { type: "set_switch", label: "Move switch", description: "Straight or diverge" },
  { type: "wait", label: "Wait", description: "Delay nested steps" },
  {
    type: "set_train_speed",
    label: "Set train speed",
    description: "Drive the detected train",
  },
  {
    type: "on_count",
    label: "Count detections",
    description: "Run nested steps once or repeatedly",
  },
];

export function AddStepMenu({
  onAdd,
  label = "Add step",
  hasSwitches,
}: {
  readonly onAdd: (type: AutomationNodeType) => void;
  readonly label?: string;
  readonly hasSwitches: boolean;
}) {
  return (
    <Menu shadow="md" width={250} position="bottom-start">
      <Menu.Target>
        <Button variant="light" size="xs">
          + {label}
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>What should happen?</Menu.Label>
        {STEP_TYPES.map((step) => (
          <Menu.Item
            key={step.type}
            disabled={step.type === "set_switch" && !hasSwitches}
            onClick={() => onAdd(step.type)}
          >
            <div>{step.label}</div>
            <div style={{ fontSize: "var(--mantine-font-size-xs)", opacity: 0.65 }}>
              {step.description}
            </div>
          </Menu.Item>
        ))}
      </Menu.Dropdown>
    </Menu>
  );
}
