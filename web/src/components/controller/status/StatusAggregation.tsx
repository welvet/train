import { Badge, Group, Paper, Stack, Text } from "@mantine/core";
import { useState } from "react";

import type { AutomationDocument, AutomationTopology } from "@/src/components/automation/types";
import type { SystemModel } from "@/src/model/system";
import { ArduinoHubRow } from "./rows/ArduinoHubRow";
import { TrainRow } from "./rows/TrainRow";
import { StatusGroup } from "./StatusGroup";

export function StatusAggregation({ system }: { readonly system: SystemModel }) {
  const [automationDocument, setAutomationDocument] = useState<AutomationDocument>({
    version: 1,
    rules: [],
  });
  const topology: AutomationTopology = {
    trainIds: system.trains.map((train) => train.id),
    switches: system.arduinoHubs.flatMap((hub) =>
      hub.switches.map((railwaySwitch) => ({ hubId: hub.id, switchId: railwaySwitch.id })),
    ),
    detectors: system.arduinoHubs.flatMap((hub) =>
      hub.detectors.map((detector) => ({ hubId: hub.id, detectorId: detector.id })),
    ),
  };
  return (
    <Stack gap="lg">
      <Paper withBorder radius="md" p="md">
        <Group justify="space-between">
          <div>
            <Text fw={700}>Backend</Text>
            <Text size="sm" c="dimmed">
              Updated {new Date(system.updatedAt).toLocaleTimeString()}
            </Text>
          </div>
          <Group gap="xs">
            <Badge color={system.running ? "green" : "red"} variant="light">
              {system.running ? "Running" : "Stopped"}
            </Badge>
            <Badge color={system.automationHalted ? "yellow" : "blue"} variant="light">
              Automation {system.automationHalted ? "halted" : "active"}
            </Badge>
          </Group>
        </Group>
      </Paper>

      <StatusGroup
        title="Trains"
        empty="No trains are configured."
        isEmpty={system.trains.length === 0}
      >
        {system.trains.map((train) => (
          <TrainRow key={train.id} train={train} />
        ))}
      </StatusGroup>

      <StatusGroup
        title="Arduino hubs"
        empty="No Arduino hubs are configured."
        isEmpty={system.arduinoHubs.length === 0}
      >
        {system.arduinoHubs.map((hub) => (
          <ArduinoHubRow
            key={hub.id}
            hub={hub}
            topology={topology}
            automationDocument={automationDocument}
            onAutomationDocumentChange={setAutomationDocument}
          />
        ))}
      </StatusGroup>
    </Stack>
  );
}
