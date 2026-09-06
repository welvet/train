"use client";

import Locomotive from "@fluentui-emoji/react/flat/locomotive";
import { Badge, Burger, Button, Group, Stack, Text, Title } from "@mantine/core";

import { useSystem } from "@/src/state/SystemProvider";

interface AppHeaderProps {
  readonly menuOpened: boolean;
  readonly onMenuToggle: () => void;
}

const connectionPresentation = {
  loading: { color: "gray", label: "Connecting" },
  online: { color: "green", label: "Online" },
  stale: { color: "yellow", label: "Updating" },
  offline: { color: "red", label: "Offline" },
} as const;

export function AppHeader({ menuOpened, onMenuToggle }: AppHeaderProps) {
  const { actions, connection, model, pendingResources, refreshing } = useSystem();
  const presentation = connectionPresentation[connection];
  const automationPending = pendingResources.has("automation");

  return (
    <Group h="100%" px={{ base: "sm", sm: "lg" }} justify="space-between" wrap="nowrap">
      <Group gap="sm" wrap="nowrap">
        <Burger
          opened={menuOpened}
          onClick={onMenuToggle}
          size="sm"
          aria-label="Toggle navigation"
        />
        <Locomotive width={38} title="Train control" />
        <Stack gap={0}>
          <Title order={2} size="h3" visibleFrom="xs">
            Railway control
          </Title>
          <Title order={2} size="h3" hiddenFrom="xs">
            Railway
          </Title>
          <Text size="xs" c="dimmed" visibleFrom="xs">
            {model ? `Revision ${model.revision}` : "Waiting for system state"}
          </Text>
        </Stack>
      </Group>

      <Group gap="xs" wrap="nowrap">
        <Badge color={presentation.color} variant="light" visibleFrom="xs">
          {refreshing && connection === "online" ? "Refreshing" : presentation.label}
        </Badge>
        <Badge color={presentation.color} variant="dot" hiddenFrom="xs" px="xs">
          {connection === "online" ? "On" : presentation.label}
        </Badge>
        {model && (
          <Button
            color={model.automationHalted ? "green" : "red"}
            variant="light"
            loading={automationPending}
            disabled={connection !== "online"}
            onClick={() => {
              void actions
                .setAutomationHalted(!model.automationHalted)
                .catch(() => undefined);
            }}
          >
            {model.automationHalted ? "Resume" : "Halt"}
          </Button>
        )}
      </Group>
    </Group>
  );
}
