import { Button, SimpleGrid, VisuallyHidden } from "@mantine/core";

import type { SetTrainSpeedNode } from "../types";
import classes from "../automation.module.css";

const STANDARD_SPEEDS = [-100, -50, 0, 50, 100] as const;

export function SetTrainSpeedEditor({
  node,
  onChange,
}: {
  readonly node: SetTrainSpeedNode;
  readonly onChange: (node: SetTrainSpeedNode) => void;
}) {
  const speeds = STANDARD_SPEEDS.includes(node.speed as (typeof STANDARD_SPEEDS)[number])
    ? STANDARD_SPEEDS
    : [...STANDARD_SPEEDS, node.speed];

  return (
    <fieldset className={classes.choiceFieldset}>
      <VisuallyHidden component="legend">Choose train speed</VisuallyHidden>
      <SimpleGrid cols={{ base: 3, sm: speeds.length }} spacing="xs">
        {speeds.map((speed) => (
          <Button
            key={speed}
            variant={node.speed === speed ? "filled" : "light"}
            size="lg"
            className={classes.choiceButton}
            onClick={() => onChange({ ...node, speed })}
            aria-label={speed === 0 ? "Stop train" : `Set train speed to ${speed}%`}
            aria-pressed={node.speed === speed}
          >
            <span aria-hidden>{speed < 0 ? "◀️" : speed > 0 ? "▶️" : "⏹️"}</span>
            <span>{speed === 0 ? "Stop" : `${Math.abs(speed)}%`}</span>
          </Button>
        ))}
      </SimpleGrid>
    </fieldset>
  );
}
