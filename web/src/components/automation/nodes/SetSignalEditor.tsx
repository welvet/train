import { NumberInput, Select, SimpleGrid } from "@mantine/core";
import { useState } from "react";

import type { SetSignalNode } from "../types";
import { signalValueError } from "./SignalConditionEditor";

export function SetSignalEditor({
  node,
  signals,
  onChange,
}: {
  readonly node: SetSignalNode;
  readonly signals: readonly string[];
  readonly onChange: (node: SetSignalNode) => void;
}) {
  const [draft, setDraft] = useState<{ source: number; value: number | string }>({
    source: node.value,
    value: node.value,
  });
  const inputValue = draft.source === node.value ? draft.value : node.value;
  const inputError = signalValueError(inputValue);

  return (
    <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
      <Select
        label="Signal"
        data={signals.map((signal) => ({ value: signal, label: signal }))}
        value={node.signal}
        allowDeselect={false}
        onChange={(signal) => signal && onChange({ ...node, signal })}
      />
      <NumberInput
        label="Value"
        value={inputValue}
        min={Number.MIN_SAFE_INTEGER}
        max={Number.MAX_SAFE_INTEGER}
        step={1}
        clampBehavior="none"
        error={inputError}
        onChange={(value) => {
          setDraft({ source: node.value, value });
          if (signalValueError(value) || typeof value !== "number") return;
          onChange({ ...node, value });
        }}
        onBlur={() => {
          if (inputError) setDraft({ source: node.value, value: node.value });
        }}
      />
    </SimpleGrid>
  );
}
