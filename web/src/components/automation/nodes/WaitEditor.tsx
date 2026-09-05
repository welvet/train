import { Button, SimpleGrid, VisuallyHidden } from "@mantine/core";

import type { WaitNode } from "../types";
import classes from "../automation.module.css";

const STANDARD_DELAYS = [1, 2, 5, 10] as const;

export function WaitEditor({
  node,
  onChange,
}: {
  readonly node: WaitNode;
  readonly onChange: (node: WaitNode) => void;
}) {
  const delays = STANDARD_DELAYS.includes(node.seconds as (typeof STANDARD_DELAYS)[number])
    ? STANDARD_DELAYS
    : [...STANDARD_DELAYS, node.seconds];

  return (
    <fieldset className={classes.choiceFieldset}>
      <VisuallyHidden component="legend">Choose how long to wait</VisuallyHidden>
      <SimpleGrid cols={{ base: 3, sm: delays.length }} spacing="xs">
        {delays.map((seconds) => (
          <Button
            key={seconds}
            variant={node.seconds === seconds ? "filled" : "light"}
            size="lg"
            className={classes.choiceButton}
            onClick={() => onChange({ ...node, seconds })}
            aria-label={`Wait ${seconds} seconds`}
            aria-pressed={node.seconds === seconds}
          >
            <span aria-hidden>⏱️</span>
            <span>{seconds}s</span>
          </Button>
        ))}
      </SimpleGrid>
    </fieldset>
  );
}
