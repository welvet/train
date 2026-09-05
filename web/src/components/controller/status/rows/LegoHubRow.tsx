import Battery from "@fluentui-emoji/react/flat/battery";
import { Badge, Text } from "@mantine/core";

import type { LegoHubModel } from "@/src/model/system";
import { DeviceRow } from "../DeviceRow";
import { StatusBadge } from "../StatusBadge";

export function LegoHubRow({ hub }: { readonly hub: LegoHubModel }) {
  return (
    <DeviceRow
      icon={<Battery width={32} aria-hidden />}
      kind="LEGO hub"
      title={hub.id}
      summary={
        <>
          <StatusBadge connected={hub.connected} />
          <Badge variant="outline">{hub.batteryPct}%</Badge>
          <Text size="sm" c="dimmed">
            {hub.voltage.toFixed(2)} V
          </Text>
        </>
      }
    />
  );
}
