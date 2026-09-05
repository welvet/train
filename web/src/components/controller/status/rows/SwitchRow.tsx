"use client";

import ControlKnobs from "@fluentui-emoji/react/flat/control-knobs";
import { Button, Group, Text } from "@mantine/core";

import type { SwitchModel } from "@/src/model/system";
import { useSystem } from "@/src/state/SystemProvider";
import { DeviceRow } from "../DeviceRow";

interface SwitchRowProps {
  readonly hubId: string;
  readonly connected: boolean;
  readonly item: SwitchModel;
}

export function SwitchRow({ hubId, connected, item }: SwitchRowProps) {
  const { actions, connection, pendingResources } = useSystem();
  const pending = pendingResources.has(`switch:${hubId}:${item.id}`);
  const controlsDisabled = !connected || connection !== "online";

  return (
    <DeviceRow
      icon={<ControlKnobs width={32} aria-hidden />}
      kind="Switch"
      title={item.id}
      summary={<Text fw={700}>{item.angle}°</Text>}
      controls={
        <Group gap="xs">
          <Button
            variant="light"
            loading={pending}
            disabled={controlsDisabled}
            aria-label={`Set switch ${item.id} on ${hubId} to straight`}
            onClick={() => {
              void actions
                .setSwitchPosition(hubId, item.id, "straight")
                .catch(() => undefined);
            }}
          >
            Straight
          </Button>
          <Button
            variant="light"
            loading={pending}
            disabled={controlsDisabled}
            aria-label={`Set switch ${item.id} on ${hubId} to diverge`}
            onClick={() => {
              void actions
                .setSwitchPosition(hubId, item.id, "diverge")
                .catch(() => undefined);
            }}
          >
            Diverge
          </Button>
        </Group>
      }
    />
  );
}
