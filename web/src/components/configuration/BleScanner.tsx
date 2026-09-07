"use client";

import { Alert, Button, Card, Code, Group, Stack, Text, Title } from "@mantine/core";
import { useMutation } from "@tanstack/react-query";
import { useMemo } from "react";

import { TrainApiClient } from "@/src/api/train-api-client";

export function BleScanner() {
  const apiClient = useMemo(() => new TrainApiClient(), []);
  const scanMutation = useMutation({
    mutationFn: () => apiClient.scanBleDevices(),
  });

  return (
    <Card withBorder radius="md" p="lg">
      <Stack gap="md">
        <Group justify="space-between" align="end">
          <div>
            <Title order={2} size="h3">Nearby LEGO hubs</Title>
            <Text size="sm" c="dimmed">
              Scan from the backend server for Powered Up hubs in pairing mode.
              Power down connected train hubs first so active control is not disturbed.
            </Text>
          </div>
          <Button
            loading={scanMutation.isPending}
            onClick={() => void scanMutation.mutateAsync().catch(() => undefined)}
          >
            Scan for LEGO hubs
          </Button>
        </Group>

        {scanMutation.error && (
          <Alert color="red" title="BLE scan failed">
            {errorMessage(scanMutation.error)}
          </Alert>
        )}

        {scanMutation.data && scanMutation.data.devices.length === 0 && (
          <Alert color="yellow" title="No LEGO hubs found" role="status">
            Make sure the hub is on and its LED is blinking, then scan again.
          </Alert>
        )}

        {scanMutation.data && scanMutation.data.devices.length > 0 && (
          <Stack gap="xs" role="list" aria-label="Discovered LEGO hubs">
            {scanMutation.data.devices.map((device) => (
              <Group
                key={device.address}
                justify="space-between"
                wrap="nowrap"
                role="listitem"
              >
                <Text>{device.name || "Unnamed LEGO hub"}</Text>
                <Code>{device.address}</Code>
              </Group>
            ))}
          </Stack>
        )}
      </Stack>
    </Card>
  );
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The backend could not scan for hubs.";
}
