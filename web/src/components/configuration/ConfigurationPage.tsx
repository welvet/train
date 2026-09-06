"use client";

import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Center,
  Group,
  Loader,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import {
  type TrainConfiguration,
  type TrainsConfiguration,
  TrainApiClient,
} from "@/src/api/train-api-client";
import { ArduinoConfigurationSection } from "./ArduinoConfigurationSection";

const CONFIGURATION_QUERY_KEY = ["configuration"] as const;

interface ConfigurationDraft {
  readonly baseModifiedAt: number;
  readonly value: TrainsConfiguration;
}

export function ConfigurationPage() {
  const queryClient = useQueryClient();
  const apiClient = useMemo(() => new TrainApiClient(), []);
  const [draftOverride, setDraftOverride] = useState<ConfigurationDraft | null>(
    null,
  );
  const configurationQuery = useQuery({
    queryKey: CONFIGURATION_QUERY_KEY,
    queryFn: ({ signal }) => apiClient.getConfiguration(signal),
    staleTime: 1_000,
  });
  const stored = configurationQuery.data?.documents.trains;
  const draft = draftOverride?.value ?? stored?.value ?? null;
  const dirty = draft !== null && stored !== undefined && !same(draft, stored.value);

  const saveMutation = useMutation({
    mutationFn: async (draft: ConfigurationDraft) => {
      if (!stored) {
        throw new Error("Train configuration has not loaded yet");
      }
      return apiClient.replaceConfiguration({
        version: 1,
        documents: {
          trains: {
            base_modified_at: draft.baseModifiedAt,
            value: draft.value,
          },
        },
      });
    },
    onSuccess: (configuration) => {
      queryClient.setQueryData(CONFIGURATION_QUERY_KEY, configuration);
      setDraftOverride(null);
    },
    onError: () => {
      void queryClient.invalidateQueries({ queryKey: CONFIGURATION_QUERY_KEY });
    },
  });

  if (!draft || !stored) {
    if (configurationQuery.isLoading) {
      return (
        <Center mih="60dvh">
          <Stack align="center">
            <Loader />
            <Text c="dimmed">Loading railway configuration…</Text>
          </Stack>
        </Center>
      );
    }
    return (
      <Center mih="60dvh">
        <Stack align="center" maw={440}>
          <Title order={2}>Configuration unavailable</Title>
          <Text c="dimmed" ta="center">
            {errorMessage(configurationQuery.error)}
          </Text>
          <Button onClick={() => void configurationQuery.refetch()}>Try again</Button>
        </Stack>
      </Center>
    );
  }

  const updateTrain = (index: number, next: TrainConfiguration) => {
    updateDraft({
      trains: draft.trains.map((train, trainIndex) =>
        trainIndex === index ? next : train,
      ),
    });
  };

  const updateDraft = (value: TrainsConfiguration) => {
    saveMutation.reset();
    setDraftOverride((current) => ({
      baseModifiedAt: current?.baseModifiedAt ?? stored.modified_at,
      value,
    }));
  };

  return (
    <Stack gap="lg" maw={1050} mx="auto">
      <Group justify="space-between" align="end">
        <div>
          <Title order={1}>Configuration</Title>
          <Text c="dimmed">
            Edit the installation settings stored by the backend.
          </Text>
        </div>
        <Badge color={dirty ? "orange" : "green"} variant="light">
          {dirty ? "Unsaved" : "Saved"}
        </Badge>
      </Group>

      {stored.restart_required && (
        <Alert color="blue" title="Saving restarts the backend">
          Train and Arduino topology changes activate automatically after saving.
          Device identity and connection changes also require local synchronization
          and firmware upload; port and FQBN only affect provisioning, Wi-Fi secrets
          stay local, and removed boards are rejected until restored or reprovisioned.
        </Alert>
      )}
      {saveMutation.error && (
        <Alert color="red" title="Could not save configuration">
          {errorMessage(saveMutation.error)}
        </Alert>
      )}

      <Group justify="space-between">
        <div>
          <Title order={2} size="h3">Trains</Title>
          <Text size="sm" c="dimmed">
            LEGO hub identity, BLE address, and every NFC tag attached to each train.
          </Text>
        </div>
        <Button
          variant="light"
          disabled={saveMutation.isPending}
          onClick={() => updateDraft({
            trains: [...draft.trains, newTrain(draft.trains)],
          })}
        >
          Add train
        </Button>
      </Group>

      <Stack gap="md">
        {draft.trains.map((train, index) => (
          <Card key={index} withBorder radius="md" p="lg">
            <Stack gap="md">
              <Group justify="space-between">
                <Text fw={700}>{train.id || `Train ${index + 1}`}</Text>
                <ActionIcon
                  color="red"
                  variant="subtle"
                  aria-label={`Remove ${train.id || `train ${index + 1}`}`}
                  disabled={draft.trains.length === 1 || saveMutation.isPending}
                  onClick={() => updateDraft({
                    trains: draft.trains.filter((_, trainIndex) => trainIndex !== index),
                  })}
                >
                  ×
                </ActionIcon>
              </Group>
              <SimpleGrid cols={{ base: 1, sm: 3 }}>
                <TextInput
                  label="Train ID"
                  value={train.id}
                  disabled={saveMutation.isPending}
                  onChange={(event) => updateTrain(index, {
                    ...train,
                    id: event.currentTarget.value,
                  })}
                />
                <TextInput
                  label="LEGO hub ID"
                  value={train.lego_hub_id}
                  disabled={saveMutation.isPending}
                  onChange={(event) => updateTrain(index, {
                    ...train,
                    lego_hub_id: event.currentTarget.value,
                  })}
                />
                <TextInput
                  label="BLE address"
                  value={train.ble_address}
                  disabled={saveMutation.isPending}
                  onChange={(event) => updateTrain(index, {
                    ...train,
                    ble_address: event.currentTarget.value,
                  })}
                />
              </SimpleGrid>
              <TextInput
                label="NFC tag IDs"
                description="Separate multiple tag UIDs with commas"
                placeholder="04:A1:B2:C3, 04:D4:E5:F6"
                value={train.tag_ids.join(", ")}
                disabled={saveMutation.isPending}
                onChange={(event) => updateTrain(index, {
                  ...train,
                  tag_ids: event.currentTarget.value
                    .split(",")
                    .map((tagId) => tagId.trim())
                    .filter(Boolean),
                })}
              />
            </Stack>
          </Card>
        ))}
      </Stack>

      <Group justify="flex-end">
        <Button
          variant="default"
          disabled={!dirty || saveMutation.isPending}
          onClick={() => {
            saveMutation.reset();
            setDraftOverride(null);
          }}
        >
          Discard changes
        </Button>
        <Button
          loading={saveMutation.isPending}
          disabled={!dirty || draftOverride === null}
          onClick={() => {
            if (draftOverride !== null) {
              void saveMutation.mutateAsync(draftOverride).catch(() => undefined);
            }
          }}
        >
          Save and restart
        </Button>
      </Group>

      <ArduinoConfigurationSection
        stored={configurationQuery.data?.documents.arduinos}
        onSaved={(configuration) => {
          queryClient.setQueryData(CONFIGURATION_QUERY_KEY, configuration);
        }}
      />
    </Stack>
  );
}

function newTrain(trains: readonly TrainConfiguration[]): TrainConfiguration {
  let suffix = trains.length + 1;
  while (trains.some((train) => train.id === `train_${suffix}`)) {
    suffix += 1;
  }
  return {
    id: `train_${suffix}`,
    lego_hub_id: `train_${suffix}`,
    ble_address: "",
    tag_ids: [],
  };
}

function same(left: TrainsConfiguration, right: TrainsConfiguration): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The backend did not return configuration.";
}
