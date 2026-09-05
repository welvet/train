"use client";

import { Alert, Button, Center, Loader, Stack, Text, Title } from "@mantine/core";

import { StatusAggregation } from "./status/StatusAggregation";
import { useSystem } from "@/src/state/SystemProvider";

export function MainController() {
  const {
    actions,
    commandError,
    connection,
    error,
    liveUpdateError,
    model,
  } = useSystem();

  if (!model && connection === "loading") {
    return (
      <Center mih="60dvh">
        <Stack align="center">
          <Loader />
          <Text c="dimmed">Connecting to the railway…</Text>
        </Stack>
      </Center>
    );
  }

  if (!model) {
    return (
      <Center mih="60dvh">
        <Stack align="center" maw={420}>
          <Title order={2}>Railway unavailable</Title>
          <Text c="dimmed" ta="center">
            {error ?? "The backend did not return system state."}
          </Text>
          <Button onClick={() => void actions.refresh()}>Try again</Button>
        </Stack>
      </Center>
    );
  }

  return (
    <Stack gap="lg" maw={1100} mx="auto">
      <div>
        <Title order={1}>System status</Title>
        <Text c="dimmed">
          Devices, sensors, and the controls currently exposed by the backend.
        </Text>
      </div>
      {connection === "stale" && (
        <Alert color="yellow" title="Showing the last known state">
          {error ?? "The latest refresh failed. The app will keep trying."}
        </Alert>
      )}
      {connection === "online" && liveUpdateError && (
        <Alert color="yellow" title="Live updates reconnecting">
          {liveUpdateError}. Controls remain available using periodic refresh.
        </Alert>
      )}
      {commandError && (
        <Alert color="red" title="Command failed">
          {commandError}
        </Alert>
      )}
      <StatusAggregation system={model} />
    </Stack>
  );
}
