import { NumberInput, Select, SimpleGrid } from "@mantine/core";
import { useState } from "react";

import type {
  IfSignalNode,
  OnSignalNode,
  SignalOperator,
  WhenSignalIsNode,
} from "../types";

type SignalConditionNode = OnSignalNode | IfSignalNode | WhenSignalIsNode;

const OPERATORS: readonly { value: SignalOperator; label: string }[] = [
  { value: "eq", label: "Equals" },
  { value: "not_eq", label: "Does not equal" },
  { value: "less", label: "Less than" },
  { value: "more", label: "More than" },
];

export function SignalConditionEditor({
  node,
  signals,
  onChange,
}: {
  readonly node: SignalConditionNode;
  readonly signals: readonly string[];
  readonly onChange: (node: SignalConditionNode) => void;
}) {
  const [draft, setDraft] = useState<{ source: number; value: number | string }>({
    source: node.value,
    value: node.value,
  });
  const inputValue = draft.source === node.value ? draft.value : node.value;
  const inputError = signalValueError(inputValue);

  return (
    <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="xs">
      <Select
        label="Signal"
        data={signals.map((signal) => ({ value: signal, label: signal }))}
        value={node.signal}
        allowDeselect={false}
        onChange={(signal) => signal && onChange({ ...node, signal })}
      />
      <Select
        label="Condition"
        data={OPERATORS}
        value={node.operator}
        allowDeselect={false}
        onChange={(operator) =>
          operator && onChange({ ...node, operator: operator as SignalOperator })
        }
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

export function signalValueError(value: number | string): string | undefined {
  if (typeof value !== "number" || !Number.isSafeInteger(value)) {
    return "Enter a safe whole number";
  }
  return undefined;
}
