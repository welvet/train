import SatelliteAntenna from "@fluentui-emoji/react/flat/satellite-antenna";
import { Badge, Text } from "@mantine/core";

import type { DetectorModel } from "@/src/model/system";
import { DeviceRow } from "../DeviceRow";

export function DetectorRow({ detector }: { readonly detector: DetectorModel }) {
  return (
    <DeviceRow
      icon={<SatelliteAntenna width={32} aria-hidden />}
      kind="Detector"
      title={detector.id}
      summary={
        <>
          <Badge color={detector.available ? "green" : "gray"} variant="light">
            {detector.available ? "Available" : "Unavailable"}
          </Badge>
          {detector.unknownTagId ? (
            <>
              <Badge color="orange" variant="light">
                Unknown tag
              </Badge>
              <Text size="sm" fw={700} ff="monospace">
                {detector.unknownTagId}
              </Text>
            </>
          ) : (
            <Text size="sm" fw={detector.triggered ? 700 : 400}>
              {detector.triggered && detector.trainId
                ? `Detected ${detector.trainId}`
                : "Clear"}
            </Text>
          )}
        </>
      }
    />
  );
}
