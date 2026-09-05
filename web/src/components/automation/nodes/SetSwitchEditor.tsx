import {
  Button,
  NativeSelect,
  SimpleGrid,
  Stack,
  VisuallyHidden,
} from "@mantine/core";

import type { SetSwitchNode, SwitchOption } from "../types";
import classes from "../automation.module.css";

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
  const targetIsConfigured = switches.some(
    (option) => option.hubId === node.hub_id && option.switchId === node.switch_id,
  );
  const duplicateIds = new Set(
    switches
      .map((option) => option.switchId)
      .filter((switchId, index, ids) => ids.indexOf(switchId) !== index),
  );
  const options = switches.map((option) => ({
    value: switchValue(option),
    label: duplicateIds.has(option.switchId)
      ? `🚦 ${option.hubId} / ${option.switchId}`
      : `🚦 ${option.switchId}`,
  }));
  if (!targetIsConfigured) {
    options.unshift({
      value: switchValue({ hubId: node.hub_id, switchId: node.switch_id }),
      label: `⚠️ Missing ${node.hub_id} / ${node.switch_id}`,
    });
  }

  return (
    <Stack gap="xs">
      {(switches.length > 1 || !targetIsConfigured) && (
        <NativeSelect
          aria-label="Choose switch"
          size="lg"
          data={options}
          value={switchValue({ hubId: node.hub_id, switchId: node.switch_id })}
          disabled={switches.length === 0}
          onChange={(event) => {
            const [hub_id, switch_id] = event.currentTarget.value.split("\u0000");
            onChange({ ...node, hub_id, switch_id });
          }}
        />
      )}
      <fieldset className={classes.choiceFieldset}>
        <VisuallyHidden component="legend">Choose a switch direction</VisuallyHidden>
        <SimpleGrid cols={2} spacing="xs">
          <Button
            variant={node.position === "straight" ? "filled" : "light"}
            size="lg"
            className={classes.choiceButton}
            onClick={() => onChange({ ...node, position: "straight" })}
            aria-label="Set switch straight"
            aria-pressed={node.position === "straight"}
          >
            <span aria-hidden>⬆️</span>
            <span>Straight</span>
          </Button>
          <Button
            variant={node.position === "diverge" ? "filled" : "light"}
            size="lg"
            className={classes.choiceButton}
            onClick={() => onChange({ ...node, position: "diverge" })}
            aria-label="Set switch to turn"
            aria-pressed={node.position === "diverge"}
          >
            <span aria-hidden>↗️</span>
            <span>Turn</span>
          </Button>
        </SimpleGrid>
      </fieldset>
    </Stack>
  );
}
