import { Button, SimpleGrid, VisuallyHidden } from "@mantine/core";

import type { OnCountNode } from "../types";
import classes from "../automation.module.css";

const STANDARD_COUNTS = [1, 2, 3, 5, 10] as const;

export function OnCountEditor({
  node,
  onChange,
}: {
  readonly node: OnCountNode;
  readonly onChange: (node: OnCountNode) => void;
}) {
  const counts = STANDARD_COUNTS.includes(node.count as (typeof STANDARD_COUNTS)[number])
    ? STANDARD_COUNTS
    : [...STANDARD_COUNTS, node.count];

  return (
    <fieldset className={classes.choiceFieldset}>
      <VisuallyHidden component="legend">Choose repeat interval</VisuallyHidden>
      <SimpleGrid cols={{ base: 3, sm: counts.length }} spacing="xs">
        {counts.map((count) => (
          <Button
            key={count}
            variant={node.count === count ? "filled" : "light"}
            size="md"
            className={classes.choiceButton}
            onClick={() => onChange({ ...node, count })}
            aria-label={
              count === 1 ? "Run on every detection" : `Run every ${count} detections`
            }
            aria-pressed={node.count === count}
          >
            <span aria-hidden>🔢</span>
            <span>{count}</span>
          </Button>
        ))}
      </SimpleGrid>
    </fieldset>
  );
}
