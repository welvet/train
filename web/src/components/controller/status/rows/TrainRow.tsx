"use client";

import Locomotive from "@fluentui-emoji/react/flat/locomotive";
import { Button, Group, Text } from "@mantine/core";

import type { TrainModel } from "@/src/model/system";
import { useSystem } from "@/src/state/SystemProvider";
import { DeviceRow } from "../DeviceRow";
import { StatusGroup } from "../StatusGroup";
import { LegoHubRow } from "./LegoHubRow";

const TRAIN_SPEEDS = [-100, -80, -50, -30, 0, 30, 50, 80, 100] as const;

export function TrainRow({ train }: { readonly train: TrainModel }) {
  const { actions, connection, pendingResources } = useSystem();
  const pending = pendingResources.has(`train:${train.id}`);
  const controlsDisabled = !train.legoHub?.connected || connection !== "online";

  return (
    <DeviceRow
      icon={<Locomotive width={36} aria-hidden />}
      kind="Train"
      title={train.id}
      summary={<Text fw={700}>{train.speed}% speed</Text>}
      controls={
        <Group gap="xs" wrap="wrap">
          {TRAIN_SPEEDS.map((speed) => {
            const stopped = speed === 0;
            const selected = train.speed === speed;

            return (
              <Button
                key={speed}
                size="compact-sm"
                color={stopped ? "red" : "blue"}
                variant={selected ? "filled" : "light"}
                disabled={pending || controlsDisabled || selected}
                aria-label={
                  stopped ? `Stop ${train.id}` : `Set ${train.id} speed to ${speed}%`
                }
                onClick={() => {
                  void actions.setTrainSpeed(train.id, speed).catch(() => undefined);
                }}
              >
                {stopped ? "STOP" : speed}
              </Button>
            );
          })}
        </Group>
      }
    >
      <StatusGroup
        title="LEGO hub"
        empty="No LEGO hub is linked to this train."
        isEmpty={!train.legoHub}
        nested
      >
        {train.legoHub && <LegoHubRow hub={train.legoHub} />}
      </StatusGroup>
    </DeviceRow>
  );
}
