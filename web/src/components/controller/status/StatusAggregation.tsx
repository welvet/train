import { Alert, Badge, Button, Group, Paper, Stack, Text } from "@mantine/core";
import { useMemo, useState } from "react";

import { serializeAutomation } from "@/src/components/automation/automation-json";
import { validateAutomationTopology } from "@/src/components/automation/automation-validation";
import type { AutomationDocument, AutomationTopology } from "@/src/components/automation/types";
import type { SystemModel } from "@/src/model/system";
import { ArduinoHubRow } from "./rows/ArduinoHubRow";
import { TrainRow } from "./rows/TrainRow";
import { StatusGroup } from "./StatusGroup";

export function StatusAggregation({
  system,
  automationSaving,
  onReplaceAutomation,
}: {
  readonly system: SystemModel;
  readonly automationSaving: boolean;
  readonly onReplaceAutomation: (
    document: AutomationDocument,
  ) => Promise<AutomationDocument>;
}) {
  const authoritativeJson = useMemo(
    () => serializeAutomation(system.automationDocument),
    [system.automationDocument],
  );
  const [automationDocument, setAutomationDocument] = useState<AutomationDocument>(
    system.automationDocument,
  );
  const [baseJson, setBaseJson] = useState(authoritativeJson);
  const draftJson = useMemo(
    () => JSON.stringify(automationDocument),
    [automationDocument],
  );
  const dirty = draftJson !== compactJson(baseJson);
  const changedElsewhere = authoritativeJson !== baseJson;
  const topology = topologyFor(system);
  const validationError = automationValidationError(
    automationDocument,
    topology,
  );
  const invalidDormantRules = automationDocument.rules.filter(
    (rule) =>
      !rule.enabled &&
      automationValidationError({ version: 1, rules: [rule] }, topology) !== null,
  );
  const hasEmptyActiveRule = automationDocument.rules.some(
    (rule) => rule.enabled && rule.root.children.length === 0,
  );
  const visibleValidationError = hasEmptyActiveRule
    ? automationValidationError(
        {
          version: 1,
          rules: automationDocument.rules.filter(
            (rule) => !rule.enabled || rule.root.children.length > 0,
          ),
        },
        topology,
      )
    : validationError;

  const saveAutomation = async () => {
    const saved = await onReplaceAutomation(automationDocument);
    const savedJson = serializeAutomation(saved);
    setAutomationDocument(saved);
    setBaseJson(savedJson);
  };

  const reloadAutomation = () => {
    setAutomationDocument(system.automationDocument);
    setBaseJson(authoritativeJson);
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

      <Paper withBorder radius="md" p="md">
        <Group justify="space-between" align="center" wrap="wrap">
          <Group gap="xs">
            <Text fw={800}>Automation</Text>
            <Badge
              color={changedElsewhere ? "orange" : dirty ? "yellow" : "green"}
              variant="light"
              size="lg"
            >
              {changedElsewhere
                ? "Changed elsewhere"
                : dirty
                  ? "Unsaved"
                  : "Saved"}
            </Badge>
          </Group>
          <Button
            size="lg"
            loading={automationSaving}
            disabled={!dirty || changedElsewhere || validationError !== null}
            onClick={() => void saveAutomation().catch(() => undefined)}
            aria-label="Save automation"
          >
            💾 Save
          </Button>
        </Group>
        {changedElsewhere && (
          <Alert color="orange" title="Active automation changed" mt="sm">
            <Stack gap="xs" align="flex-start">
              <Text size="sm">
                {dirty
                  ? "Reload the active tree before editing further so this draft does not overwrite newer changes."
                  : "Reload to display the latest active automation tree."}
              </Text>
              <Button variant="light" color="orange" size="xs" onClick={reloadAutomation}>
                Reload active automation
              </Button>
            </Stack>
          </Alert>
        )}
        {!changedElsewhere && visibleValidationError && (
          <Alert color="red" title="Automation draft cannot be saved" mt="sm">
            {invalidDormantRules.length > 0 ? (
              <Stack gap="xs" align="flex-start">
                <Text size="sm">
                  {invalidDormantRules.length === 1
                    ? "An old hidden rule no longer matches the railway."
                    : `${invalidDormantRules.length} old hidden rules no longer match the railway.`}
                </Text>
                <Button
                  color="red"
                  variant="light"
                  size="lg"
                  onClick={() => {
                    const invalidRules = new Set(invalidDormantRules);
                    setAutomationDocument({
                      version: 1,
                      rules: automationDocument.rules.filter((rule) => !invalidRules.has(rule)),
                    });
                  }}
                  aria-label="Remove dormant rules that no longer match the railway"
                >
                  🧹 Clean up
                </Button>
              </Stack>
            ) : visibleValidationError}
          </Alert>
        )}
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
            automationSaving={automationSaving}
            onAutomationDocumentChange={setAutomationDocument}
          />
        ))}
      </StatusGroup>
    </Stack>
  );
}

function compactJson(source: string): string {
  return JSON.stringify(JSON.parse(source));
}

function topologyFor(system: SystemModel): AutomationTopology {
  return {
    trainIds: system.trains.map((train) => train.id),
    switches: system.arduinoHubs.flatMap((hub) =>
      hub.switches.map((railwaySwitch) => ({
        hubId: hub.id,
        switchId: railwaySwitch.id,
      })),
    ),
    detectors: system.arduinoHubs.flatMap((hub) =>
      hub.detectors.map((detector) => ({
        hubId: hub.id,
        detectorId: detector.id,
      })),
    ),
  };
}

function automationValidationError(
  document: AutomationDocument,
  topology: AutomationTopology,
): string | null {
  try {
    serializeAutomation(document);
    validateAutomationTopology(document, topology);
    return null;
  } catch (error) {
    return error instanceof Error ? error.message : "The automation draft is invalid.";
  }
}
