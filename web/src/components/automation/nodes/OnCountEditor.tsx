import { Button, SimpleGrid, Stack, VisuallyHidden } from "@mantine/core";

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
    <Stack gap="xs">
      <fieldset className={classes.choiceFieldset}>
        <VisuallyHidden component="legend">Choose detection count</VisuallyHidden>
        <SimpleGrid cols={{ base: 3, sm: counts.length }} spacing="xs">
          {counts.map((count) => (
            <Button
              key={count}
              variant={node.count === count ? "filled" : "light"}
              size="lg"
              className={classes.choiceButton}
              onClick={() => onChange({ ...node, count })}
              aria-label={`Run on detection ${count}`}
              aria-pressed={node.count === count}
            >
              <span aria-hidden>🔢</span>
              <span>{count}</span>
            </Button>
          ))}
        </SimpleGrid>
      </fieldset>
      <fieldset className={classes.choiceFieldset}>
        <VisuallyHidden component="legend">Choose repeat behavior</VisuallyHidden>
        <SimpleGrid cols={2} spacing="xs">
          <Button
            variant={node.mode === "once" ? "filled" : "light"}
            size="lg"
            className={classes.choiceButton}
            onClick={() => onChange({ ...node, mode: "once" })}
            aria-label="Run once"
            aria-pressed={node.mode === "once"}
          >
            <span aria-hidden>1️⃣</span>
            <span>Once</span>
          </Button>
          <Button
            variant={node.mode === "repeat" ? "filled" : "light"}
            size="lg"
            className={classes.choiceButton}
            onClick={() => onChange({ ...node, mode: "repeat" })}
            aria-label="Repeat forever"
            aria-pressed={node.mode === "repeat"}
          >
            <span aria-hidden>🔁</span>
            <span>Repeat</span>
          </Button>
        </SimpleGrid>
      </fieldset>
    </Stack>
  );
}
