import { NumberInput } from "@mantine/core";
import { useState } from "react";

import type { OnCountNode } from "../types";

export function OnCountEditor({
  node,
  onChange,
}: {
  readonly node: OnCountNode;
  readonly onChange: (node: OnCountNode) => void;
}) {
  const [draft, setDraft] = useState<{ source: number; value: number | string }>({
    source: node.count,
    value: node.count,
  });
  const inputValue = draft.source === node.count ? draft.value : node.count;
  const inputError = getCountError(inputValue);

  return (
    <NumberInput
      label="Detection count"
      description="Repeat after this many detections"
      value={inputValue}
      min={1}
      step={1}
      allowNegative={false}
      clampBehavior="none"
      error={inputError}
      onChange={(count) => {
        setDraft({ source: node.count, value: count });
        if (getCountError(count)) return;
        if (typeof count !== "number") return;
        onChange({ ...node, count });
      }}
      onBlur={() => {
        if (inputError) setDraft({ source: node.count, value: node.count });
      }}
    />
  );
}

function getCountError(value: number | string): string | undefined {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    return "Enter a positive whole number";
  }
  if (value < 1) return "Detection count must be at least 1";
  return undefined;
}
