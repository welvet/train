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
  { type: "if_count", emoji: "🔀", label: "Count branch" },
  { type: "set_signal", emoji: "📶", label: "Set signal" },
  { type: "on_signal", emoji: "✅", label: "Signal" },
  { type: "if_signal", emoji: "↔️", label: "Signal branch" },
  { type: "when_signal_is", emoji: "👀", label: "Wait for signal" },
];

export function AddStepMenu({
  onAdd,
  hasSwitches,
  hasSignals,
}: {
  readonly onAdd: (type: AutomationNodeType) => void;
  readonly hasSwitches: boolean;
  readonly hasSignals: boolean;
}) {
  return (
    <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="xs">
      {STEP_TYPES.map((step) => (
        <Button
          key={step.type}
          variant="light"
          size="md"
          className={classes.pictureButton}
          disabled={
            (step.type === "set_switch" && !hasSwitches) ||
            (step.type.includes("signal") && !hasSignals)
          }
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
