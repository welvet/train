import { Box, Group, Paper, Stack, Text } from "@mantine/core";
import type { ReactNode } from "react";

import classes from "./status.module.css";

interface DeviceRowProps {
  readonly icon: ReactNode;
  readonly kind: string;
  readonly title: string;
  readonly summary: ReactNode;
  readonly controls?: ReactNode;
  readonly children?: ReactNode;
}

export function DeviceRow({
  icon,
  kind,
  title,
  summary,
  controls,
  children,
}: DeviceRowProps) {
  return (
    <li className={classes.listItem}>
      <Paper withBorder radius="md" p={{ base: "sm", sm: "md" }}>
        <Group justify="space-between" align="center" wrap="wrap" gap="md">
          <Group gap="sm" wrap="nowrap">
            <Box className={classes.icon}>{icon}</Box>
            <Stack gap={1}>
              <Text size="xs" tt="uppercase" fw={700} c="dimmed">
                {kind}
              </Text>
              <Text fw={700}>{title}</Text>
            </Stack>
          </Group>
          <Group gap="sm" className={classes.summary}>
            {summary}
          </Group>
        </Group>
        {controls && <Box mt="md">{controls}</Box>}
        {children}
      </Paper>
    </li>
  );
}
