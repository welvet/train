import { NumberInput } from "@mantine/core";

import type { SetTrainSpeedNode } from "../types";

export function SetTrainSpeedEditor({
  node,
  onChange,
}: {
  readonly node: SetTrainSpeedNode;
  readonly onChange: (node: SetTrainSpeedNode) => void;
}) {
  return (
    <NumberInput
      label="Speed"
      description="Signed percent; 0 stops the detected train"
      min={-100}
      max={100}
      step={5}
      allowDecimal={false}
      value={node.speed}
      onChange={(speed) =>
        onChange({ ...node, speed: typeof speed === "number" ? speed : 0 })
      }
    />
  );
}
