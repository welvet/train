import { Button, SimpleGrid } from "@mantine/core";

import type { AutomationNodeType } from "./node-factories";
import classes from "./automation.module.css";

const STEP_TYPES: readonly {
  type: AutomationNodeType;
  emoji: string;
  label: string;
}[] = [
  { type: "set_train_speed", emoji: "🚂", label: "Speed" },
  { type: "set_switch", emoji: "🚦", label: "Switch" },
  { type: "wait", emoji: "⏱️", label: "Wait" },
  { type: "on_count", emoji: "🔁", label: "Count" },
];

export function AddStepMenu({
  onAdd,
  hasSwitches,
}: {
  readonly onAdd: (type: AutomationNodeType) => void;
  readonly hasSwitches: boolean;
}) {
  return (
    <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="xs">
      {STEP_TYPES.map((step) => (
        <Button
          key={step.type}
          variant="light"
          size="lg"
          className={classes.pictureButton}
          disabled={step.type === "set_switch" && !hasSwitches}
          onClick={() => onAdd(step.type)}
          aria-label={`Add ${step.label.toLowerCase()} step`}
        >
          <span aria-hidden className={classes.buttonEmoji}>{step.emoji}</span>
          <span>{step.label}</span>
        </Button>
      ))}
    </SimpleGrid>
  );
}
