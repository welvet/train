"use client";

import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Divider,
  Group,
  NumberInput,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import {
  type ArduinoDeviceConfiguration,
  type ArduinoReaderConfiguration,
  type ArduinoSwitchConfiguration,
  type ArduinosConfiguration,
  type ConfigurationSnapshot,
  TrainApiClient,
} from "@/src/api/train-api-client";

interface ArduinoConfigurationSectionProps {
  readonly stored: ConfigurationSnapshot["documents"]["arduinos"];
  readonly onSaved: (configuration: ConfigurationSnapshot) => void;
}

interface ArduinoDraft {
  readonly baseModifiedAt: number;
  readonly value: ArduinosConfiguration;
}

export function ArduinoConfigurationSection({
  stored,
  onSaved,
}: ArduinoConfigurationSectionProps) {
  const apiClient = useMemo(() => new TrainApiClient(), []);
  const queryClient = useQueryClient();
  const [draftOverride, setDraftOverride] = useState<ArduinoDraft | null>(null);
  const draft = draftOverride?.value ?? stored?.value ?? null;
  const dirty = draft !== null && stored !== undefined && !same(draft, stored.value);
  const saveMutation = useMutation({
    mutationFn: (next: ArduinoDraft) => apiClient.replaceConfiguration({
      version: 1,
      documents: {
        arduinos: {
          base_modified_at: next.baseModifiedAt,
          value: next.value,
        },
      },
    }),
    onSuccess: (configuration) => {
      onSaved(configuration);
      setDraftOverride(null);
    },
    onError: () => {
      void queryClient.invalidateQueries({ queryKey: ["configuration"] });
    },
  });

  if (!stored || !draft) {
    return (
      <Card withBorder radius="md" p="lg">
        <Stack gap="xs">
          <Title order={2} size="h3">Arduino devices</Title>
          <Alert color="yellow" title="Arduino editing unavailable">
            This backend exposes train configuration only. Upgrade it to edit Arduino
            devices; train editing remains available.
          </Alert>
        </Stack>
      </Card>
    );
  }

  const updateDraft = (value: ArduinosConfiguration) => {
    saveMutation.reset();
    setDraftOverride((current) => ({
      baseModifiedAt: current?.baseModifiedAt ?? stored.modified_at,
      value,
    }));
  };
  const updateDevices = (
    devices: ArduinosConfiguration["devices"],
  ) => updateDraft({ devices });
  const entries = Object.entries(draft.devices);

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="end">
        <div>
          <Title order={2} size="h3">Arduino devices</Title>
          <Text size="sm" c="dimmed">
            Hardware topology, firmware provisioning, and local Arduino tooling.
          </Text>
        </div>
        <Group>
          <Badge color={dirty ? "orange" : "green"} variant="light">
            {dirty ? "Unsaved" : "Saved"}
          </Badge>
          <Button
            variant="light"
            disabled={saveMutation.isPending}
            onClick={() => {
              const [id, device] = newDevice(draft.devices);
              updateDevices({ ...draft.devices, [id]: device });
            }}
          >
            Add device
          </Button>
        </Group>
      </Group>

      {saveMutation.error && (
        <Alert color="red" title="Could not save Arduino configuration">
          {errorMessage(saveMutation.error)}
        </Alert>
      )}

      {entries.map(([deviceId, device], deviceIndex) => (
        <Card key={deviceIndex} withBorder radius="md" p="lg">
          <Stack gap="md">
            <Group justify="space-between">
              <Text fw={700}>{deviceId || `Device ${deviceIndex + 1}`}</Text>
              <ActionIcon
                color="red"
                variant="subtle"
                aria-label={`Remove ${deviceId || `device ${deviceIndex + 1}`}`}
                disabled={entries.length === 1 || saveMutation.isPending}
                onClick={() => {
                  const devices = { ...draft.devices };
                  delete devices[deviceId];
                  updateDevices(devices);
                }}
              >
                ×
              </ActionIcon>
            </Group>

            <Text size="sm" fw={600}>Identity and runtime topology</Text>
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
              <TextInput
                label="Device ID"
                description="Rename requires secret repair, firmware upload, and backend restart"
                value={deviceId}
                disabled={saveMutation.isPending}
                onChange={(event) => {
                  const nextId = event.currentTarget.value;
                  if (nextId !== deviceId && nextId in draft.devices) return;
                  const devices: ArduinosConfiguration["devices"] = {};
                  for (const [id, value] of Object.entries(draft.devices)) {
                    devices[id === deviceId ? nextId : id] = value;
                  }
                  updateDevices(devices);
                }}
              />
              <TextInput
                label="Hub ID"
                value={device.hub_id}
                disabled={saveMutation.isPending}
                onChange={(event) => updateDevice(
                  draft,
                  deviceId,
                  { ...device, hub_id: event.currentTarget.value },
                  updateDraft,
                )}
              />
              <NumberInput
                label="Servo settle (ms)"
                min={1}
                value={device.servo_settle_ms}
                disabled={saveMutation.isPending}
                onChange={(value) => updateDevice(
                  draft,
                  deviceId,
                  { ...device, servo_settle_ms: numeric(value) },
                  updateDraft,
                )}
              />
            </SimpleGrid>

            <Divider />
            <Text size="sm" fw={600}>Firmware provisioning</Text>
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
              <TextInput
                label="Backend host"
                value={device.backend_host}
                disabled={saveMutation.isPending}
                onChange={(event) => updateDevice(draft, deviceId, {
                  ...device,
                  backend_host: event.currentTarget.value,
                }, updateDraft)}
              />
              <NumberInput
                label="Backend port"
                min={1}
                max={65535}
                value={device.backend_port}
                disabled={saveMutation.isPending}
                onChange={(value) => updateDevice(draft, deviceId, {
                  ...device,
                  backend_port: numeric(value),
                }, updateDraft)}
              />
              <NumberInput
                label="Serial baud rate"
                min={1}
                value={device.baudrate}
                disabled={saveMutation.isPending}
                onChange={(value) => updateDevice(draft, deviceId, {
                  ...device,
                  baudrate: numeric(value),
                }, updateDraft)}
              />
              <NumberInput
                label="Reconnect delay (ms)"
                min={1}
                value={device.reconnect_ms}
                disabled={saveMutation.isPending}
                onChange={(value) => updateDevice(draft, deviceId, {
                  ...device,
                  reconnect_ms: numeric(value),
                }, updateDraft)}
              />
              <Checkbox
                mt="xl"
                label="Enable firmware event logger"
                checked={device.event_logger_enabled}
                disabled={saveMutation.isPending}
                onChange={(event) => updateDevice(draft, deviceId, {
                  ...device,
                  event_logger_enabled: event.currentTarget.checked,
                }, updateDraft)}
              />
            </SimpleGrid>

            <Divider />
            <Text size="sm" fw={600}>Provisioning workstation</Text>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <TextInput
                label="Serial port"
                value={device.port}
                disabled={saveMutation.isPending}
                onChange={(event) => updateDevice(draft, deviceId, {
                  ...device,
                  port: event.currentTarget.value,
                }, updateDraft)}
              />
              <TextInput
                label="FQBN"
                value={device.fqbn}
                disabled={saveMutation.isPending}
                onChange={(event) => updateDevice(draft, deviceId, {
                  ...device,
                  fqbn: event.currentTarget.value,
                }, updateDraft)}
              />
            </SimpleGrid>

            <ComponentList
              title="Switches"
              kind="switch"
              values={device.switches}
              reservedIds={device.readers.map((reader) => reader.id)}
              reservedPins={device.readers.map((reader) => reader.ss_pin)}
              disabled={saveMutation.isPending}
              onChange={(switches) => updateDevice(
                draft,
                deviceId,
                { ...device, switches },
                updateDraft,
              )}
            />
            <ComponentList
              title="Readers"
              kind="reader"
              values={device.readers}
              reservedIds={device.switches.map((item) => item.id)}
              reservedPins={device.switches.map((item) => item.pin)}
              disabled={saveMutation.isPending}
              onChange={(readers) => updateDevice(
                draft,
                deviceId,
                { ...device, readers },
                updateDraft,
              )}
            />
          </Stack>
        </Card>
      ))}

      <Group justify="flex-end">
        <Button
          variant="default"
          disabled={!dirty || saveMutation.isPending}
          onClick={() => {
            saveMutation.reset();
            setDraftOverride(null);
          }}
        >
          Discard Arduino changes
        </Button>
        <Button
          loading={saveMutation.isPending}
          disabled={!dirty || draftOverride === null}
          onClick={() => {
            if (draftOverride) {
              void saveMutation.mutateAsync(draftOverride).catch(() => undefined);
            }
          }}
        >
          Save Arduino configuration and restart
        </Button>
      </Group>
    </Stack>
  );
}

type ComponentListProps =
  | {
      readonly title: string;
      readonly kind: "switch";
      readonly values: ArduinoSwitchConfiguration[];
      readonly reservedIds: string[];
      readonly reservedPins: number[];
      readonly disabled: boolean;
      readonly onChange: (value: ArduinoSwitchConfiguration[]) => void;
    }
  | {
      readonly title: string;
      readonly kind: "reader";
      readonly values: ArduinoReaderConfiguration[];
      readonly reservedIds: string[];
      readonly reservedPins: number[];
      readonly disabled: boolean;
      readonly onChange: (value: ArduinoReaderConfiguration[]) => void;
    };

function ComponentList(props: ComponentListProps) {
  return props.kind === "switch" ? (
    <SwitchList {...props} />
  ) : (
    <ReaderList {...props} />
  );
}

function SwitchList(props: Extract<ComponentListProps, { kind: "switch" }>) {
  const usedPins = [
    ...props.values.map((item) => item.pin),
    ...props.reservedPins,
  ];
  return (
    <Stack gap="sm">
      <Group justify="space-between">
        <Text fw={600}>{props.title}</Text>
        <Button
          size="xs"
          variant="light"
          disabled={
            props.disabled || props.values.length >= 8 || nextPin(usedPins) === null
          }
          onClick={() => {
            const value = newSwitch(
              props.values,
              props.reservedIds,
              props.reservedPins,
            );
            if (value !== null) props.onChange([...props.values, value]);
          }}
        >
          Add switch
        </Button>
      </Group>
      {props.values.map((value, index) => (
        <Group key={index} align="end" wrap="wrap">
          <TextInput
            label="Switch ID"
            value={value.id}
            disabled={props.disabled}
            onChange={(event) => {
              const next = [...props.values];
              next[index] = { ...value, id: event.currentTarget.value };
              props.onChange(next);
            }}
          />
          <NumberInput label="Pin" min={2} max={10} value={value.pin}
            disabled={props.disabled} onChange={(nextValue) => {
              const next = [...props.values];
              next[index] = { ...value, pin: numeric(nextValue) };
              props.onChange(next);
            }} />
          <NumberInput label="Straight angle" min={0} max={180}
            value={value.straight} disabled={props.disabled}
            onChange={(nextValue) => {
              const next = [...props.values];
              next[index] = { ...value, straight: numeric(nextValue) };
              props.onChange(next);
            }} />
          <NumberInput label="Diverge angle" min={0} max={180}
            value={value.diverge} disabled={props.disabled}
            onChange={(nextValue) => {
              const next = [...props.values];
              next[index] = { ...value, diverge: numeric(nextValue) };
              props.onChange(next);
            }} />
          <ActionIcon
            color="red"
            variant="subtle"
            aria-label={`Remove switch ${value.id || index + 1}`}
            disabled={props.disabled}
            onClick={() => props.onChange(props.values.filter(
              (_, valueIndex) => valueIndex !== index,
            ))}
          >
            ×
          </ActionIcon>
        </Group>
      ))}
    </Stack>
  );
}

function ReaderList(props: Extract<ComponentListProps, { kind: "reader" }>) {
  const usedPins = [
    ...props.values.map((item) => item.ss_pin),
    ...props.reservedPins,
  ];
  return (
    <Stack gap="sm">
      <Group justify="space-between">
        <Text fw={600}>{props.title}</Text>
        <Button size="xs" variant="light"
          disabled={
            props.disabled || props.values.length >= 8 || nextPin(usedPins) === null
          }
          onClick={() => {
            const value = newReader(
              props.values,
              props.reservedIds,
              props.reservedPins,
            );
            if (value !== null) props.onChange([...props.values, value]);
          }}
        >
          Add reader
        </Button>
      </Group>
      {props.values.map((value, index) => (
        <Group key={index} align="end" wrap="wrap">
          <TextInput label="Reader ID" value={value.id} disabled={props.disabled}
            onChange={(event) => {
              const next = [...props.values];
              next[index] = { ...value, id: event.currentTarget.value };
              props.onChange(next);
            }} />
          <NumberInput label="SS pin" min={2} max={10} value={value.ss_pin}
            disabled={props.disabled} onChange={(nextValue) => {
              const next = [...props.values];
              next[index] = { ...value, ss_pin: numeric(nextValue) };
              props.onChange(next);
            }} />
          <NumberInput label="Read timeout (ms)" min={1} max={1000}
            value={value.read_timeout_ms} disabled={props.disabled}
            onChange={(nextValue) => {
              const next = [...props.values];
              next[index] = { ...value, read_timeout_ms: numeric(nextValue) };
              props.onChange(next);
            }} />
          <NumberInput label="Removal delay (ms)" min={1}
            value={value.removal_delay_ms} disabled={props.disabled}
            onChange={(nextValue) => {
              const next = [...props.values];
              next[index] = { ...value, removal_delay_ms: numeric(nextValue) };
              props.onChange(next);
            }} />
          <ActionIcon color="red" variant="subtle"
            aria-label={`Remove reader ${value.id || index + 1}`}
            disabled={props.disabled}
            onClick={() => props.onChange(props.values.filter(
              (_, valueIndex) => valueIndex !== index,
            ))}
          >
            ×
          </ActionIcon>
        </Group>
      ))}
    </Stack>
  );
}

function updateDevice(
  draft: ArduinosConfiguration,
  deviceId: string,
  device: ArduinoDeviceConfiguration,
  update: (value: ArduinosConfiguration) => void,
) {
  update({ devices: { ...draft.devices, [deviceId]: device } });
}

function newDevice(
  devices: ArduinosConfiguration["devices"],
): [string, ArduinoDeviceConfiguration] {
  let suffix = Object.keys(devices).length + 1;
  while (`arduino_${suffix}` in devices) suffix += 1;
  return [`arduino_${suffix}`, {
    port: "/dev/cu.usbmodem",
    fqbn: "arduino:renesas_uno:unor4wifi",
    baudrate: 9600,
    hub_id: `hub_${suffix}`,
    backend_host: "127.0.0.1",
    backend_port: 9000,
    servo_settle_ms: 500,
    reconnect_ms: 2000,
    event_logger_enabled: false,
    switches: [],
    readers: [],
  }];
}

function newSwitch(
  switches: readonly ArduinoSwitchConfiguration[],
  reservedIds: readonly string[],
  reservedPins: readonly number[],
): ArduinoSwitchConfiguration | null {
  const pin = nextPin([...switches.map((item) => item.pin), ...reservedPins]);
  if (pin === null) return null;
  return {
    id: nextId("S", [...switches.map((item) => item.id), ...reservedIds]),
    pin,
    straight: 60,
    diverge: 120,
  };
}

function newReader(
  readers: readonly ArduinoReaderConfiguration[],
  reservedIds: readonly string[],
  reservedPins: readonly number[],
): ArduinoReaderConfiguration | null {
  const ssPin = nextPin([
    ...readers.map((item) => item.ss_pin),
    ...reservedPins,
  ]);
  if (ssPin === null) return null;
  return {
    id: nextId("D", [...readers.map((item) => item.id), ...reservedIds]),
    ss_pin: ssPin,
    read_timeout_ms: 250,
    removal_delay_ms: 750,
  };
}

function nextId(prefix: string, used: readonly string[]): string {
  let suffix = 1;
  while (used.includes(`${prefix}${suffix}`)) suffix += 1;
  return `${prefix}${suffix}`;
}

function nextPin(used: readonly number[]): number | null {
  return [9, 8, 7, 6, 5, 4, 3, 2, 10].find((pin) => !used.includes(pin)) ?? null;
}

function numeric(value: string | number): number {
  return typeof value === "number" ? value : Number(value) || 0;
}

function same(left: ArduinosConfiguration, right: ArduinosConfiguration) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The backend rejected the Arduino configuration.";
}
