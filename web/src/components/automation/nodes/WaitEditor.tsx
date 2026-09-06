import { NumberInput } from "@mantine/core";
import { useState } from "react";

import type { WaitNode } from "../types";

export function WaitEditor({
  node,
  onChange,
}: {
  readonly node: WaitNode;
  readonly onChange: (node: WaitNode) => void;
}) {
  const [draft, setDraft] = useState<{ source: number; value: number | string }>({
    source: node.seconds,
    value: node.seconds,
  });
  const inputValue = draft.source === node.seconds ? draft.value : node.seconds;
  const inputError = getWaitError(inputValue);

  return (
    <NumberInput
      label="Wait (seconds)"
      description="Number from 0 to 3600"
      value={inputValue}
      min={0}
      max={3600}
      step={1}
      allowNegative={false}
      clampBehavior="none"
      error={inputError}
      onChange={(seconds) => {
        setDraft({ source: node.seconds, value: seconds });
        if (getWaitError(seconds)) return;
        if (typeof seconds !== "number") return;
        onChange({ ...node, seconds });
      }}
      onBlur={() => {
        if (inputError) setDraft({ source: node.seconds, value: node.seconds });
      }}
    />
  );
}

function getWaitError(value: number | string): string | undefined {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Enter a number from 0 to 3600";
  }
  if (value < 0 || value > 3600) return "Wait must be from 0 to 3600 seconds";
  return undefined;
}
