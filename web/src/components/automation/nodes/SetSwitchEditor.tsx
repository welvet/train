import { NativeSelect, SimpleGrid } from "@mantine/core";

import type { SetSwitchNode, SwitchOption } from "../types";

function switchValue(option: SwitchOption) {
  return `${option.hubId}\u0000${option.switchId}`;
}

export function SetSwitchEditor({
  node,
  switches,
  onChange,
}: {
  readonly node: SetSwitchNode;
  readonly switches: readonly SwitchOption[];
  readonly onChange: (node: SetSwitchNode) => void;
}) {
  return (
    <SimpleGrid cols={{ base: 1, sm: 2 }}>
      <NativeSelect
        label="Switch"
        data={switches.map((option) => ({
          value: switchValue(option),
          label: `${option.hubId} / ${option.switchId}`,
        }))}
        value={switchValue({ hubId: node.hub_id, switchId: node.switch_id })}
        disabled={switches.length === 0}
        onChange={(event) => {
          const value = event.currentTarget.value;
          const [hub_id, switch_id] = value.split("\u0000");
          onChange({ ...node, hub_id, switch_id });
        }}
      />
      <NativeSelect
        label="Position"
        data={[
          { value: "straight", label: "Straight" },
          { value: "diverge", label: "Diverge" },
        ]}
        value={node.position}
        onChange={(event) => {
          const position = event.currentTarget.value;
          if (position === "straight" || position === "diverge") {
            onChange({ ...node, position });
          }
        }}
      />
    </SimpleGrid>
  );
}
