"use client";

import Locomotive from "@fluentui-emoji/react/flat/locomotive";
import { Button, Group, Slider, Text } from "@mantine/core";
import { useState } from "react";

import type { TrainModel } from "@/src/model/system";
import { useSystem } from "@/src/state/SystemProvider";
import { DeviceRow } from "../DeviceRow";
import { StatusGroup } from "../StatusGroup";
import { LegoHubRow } from "./LegoHubRow";

export function TrainRow({ train }: { readonly train: TrainModel }) {
  return <TrainRowWithDraft key={`${train.id}:${train.speed}`} train={train} />;
}

function TrainRowWithDraft({ train }: { readonly train: TrainModel }) {
  const { actions, connection, pendingResources } = useSystem();
  const [draftSpeed, setDraftSpeed] = useState(train.speed);
  const pending = pendingResources.has(`train:${train.id}`);
  const controlsDisabled = !train.legoHub?.connected || connection !== "online";

  return (
    <DeviceRow
      icon={<Locomotive width={36} aria-hidden />}
      kind="Train"
      title={train.id}
      summary={<Text fw={700}>{train.speed}% speed</Text>}
      controls={
        <Group align="end" wrap="wrap">
          <Slider
            aria-label={`Speed for ${train.id}`}
            min={-100}
            max={100}
            value={draftSpeed}
            onChange={setDraftSpeed}
            disabled={pending || controlsDisabled}
            label={(value) => `${value}%`}
            style={{ flex: "1 1 220px" }}
          />
          <Button
            loading={pending}
            disabled={controlsDisabled || draftSpeed === train.speed}
            aria-label={`Apply speed for ${train.id}`}
            onClick={() => {
              void actions.setTrainSpeed(train.id, draftSpeed).catch(() => undefined);
            }}
          >
            Apply
          </Button>
          <Button
            color="red"
            variant="light"
            loading={pending}
            disabled={controlsDisabled || train.speed === 0}
            aria-label={`Stop ${train.id}`}
            onClick={() => {
              void actions.setTrainSpeed(train.id, 0).catch(() => undefined);
            }}
          >
            Stop
          </Button>
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
