import { NumberInput } from "@mantine/core";
import { useState } from "react";

import type { SetTrainSpeedNode } from "../types";

export function SetTrainSpeedEditor({
  node,
  onChange,
}: {
  readonly node: SetTrainSpeedNode;
  readonly onChange: (node: SetTrainSpeedNode) => void;
}) {
  const [draft, setDraft] = useState<{ source: number; value: number | string }>({
    source: node.speed,
    value: node.speed,
  });
  const inputValue = draft.source === node.speed ? draft.value : node.speed;
  const inputError = getSpeedError(inputValue);

  return (
    <NumberInput
      label="Train speed (%)"
      description="Whole number from -100 to 100; use 0 to stop"
      value={inputValue}
      min={-100}
      max={100}
      step={1}
      clampBehavior="none"
      error={inputError}
      onChange={(speed) => {
        setDraft({ source: node.speed, value: speed });
        if (getSpeedError(speed)) return;
        if (typeof speed !== "number") return;
        onChange({ ...node, speed });
      }}
      onBlur={() => {
        if (inputError) setDraft({ source: node.speed, value: node.speed });
      }}
    />
  );
}

function getSpeedError(value: number | string): string | undefined {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    return "Enter a whole number from -100 to 100";
  }
  if (value < -100 || value > 100) return "Speed must be from -100 to 100";
  return undefined;
}
