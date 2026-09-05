import { NativeSelect } from "@mantine/core";

import type { WaitNode } from "../types";

const WAIT_OPTIONS = Array.from({ length: 10 }, (_, index) => ({
  value: String(index + 1),
  label: `${index + 1} second${index === 0 ? "" : "s"}`,
}));

export function WaitEditor({
  node,
  onChange,
}: {
  readonly node: WaitNode;
  readonly onChange: (node: WaitNode) => void;
}) {
  const isStandardOption = Number.isInteger(node.seconds) && node.seconds >= 1 && node.seconds <= 10;
  const options = isStandardOption
    ? WAIT_OPTIONS
    : [
        ...WAIT_OPTIONS,
        {
          value: String(node.seconds),
          label: `${node.seconds} seconds (imported)`,
        },
      ];
  return (
    <NativeSelect
      label="Delay"
      description="Then run the nested steps"
      data={options}
      value={String(node.seconds)}
      onChange={(event) => {
        onChange({ ...node, seconds: Number(event.currentTarget.value) });
      }}
    />
  );
}
