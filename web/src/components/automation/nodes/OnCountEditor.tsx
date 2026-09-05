import { NativeSelect, NumberInput, SimpleGrid } from "@mantine/core";

import type { OnCountNode } from "../types";

export function OnCountEditor({
  node,
  onChange,
}: {
  readonly node: OnCountNode;
  readonly onChange: (node: OnCountNode) => void;
}) {
  return (
    <SimpleGrid cols={{ base: 1, sm: 2 }}>
      <NumberInput
        label="Occurrence"
        description="Count each accepted detection"
        min={1}
        step={1}
        value={node.count}
        onChange={(count) =>
          onChange({
            ...node,
            count: typeof count === "number" ? Math.max(1, Math.round(count)) : 1,
          })
        }
      />
      <NativeSelect
        label="Behavior"
        description="Run once or at every multiple"
        data={[
          { value: "once", label: "Only once" },
          { value: "repeat", label: "Repeat" },
        ]}
        value={node.mode}
        onChange={(event) => {
          const mode = event.currentTarget.value;
          if (mode === "once" || mode === "repeat") onChange({ ...node, mode });
        }}
      />
    </SimpleGrid>
  );
}
