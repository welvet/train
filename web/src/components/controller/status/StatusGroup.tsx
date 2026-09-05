import { Stack, Text } from "@mantine/core";
import type { ReactNode } from "react";

import classes from "./status.module.css";

interface StatusGroupProps {
  readonly title: string;
  readonly empty: string;
  readonly children: ReactNode;
  readonly isEmpty: boolean;
  readonly nested?: boolean;
}

export function StatusGroup({
  title,
  empty,
  children,
  isEmpty,
  nested = false,
}: StatusGroupProps) {
  return (
    <Stack gap="xs" mt={nested ? "md" : 0}>
      <Text fw={700} size={nested ? "sm" : "lg"}>
        {title}
      </Text>
      {isEmpty ? (
        <Text c="dimmed" size="sm">
          {empty}
        </Text>
      ) : (
        <ul className={nested ? classes.nestedList : classes.list}>{children}</ul>
      )}
    </Stack>
  );
}
