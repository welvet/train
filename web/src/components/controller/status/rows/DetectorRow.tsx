import SatelliteAntenna from "@fluentui-emoji/react/flat/satellite-antenna";
import { Badge, Text } from "@mantine/core";

import { AutomationEditor } from "@/src/components/automation/AutomationEditor";
import type { AutomationDocument, AutomationTopology } from "@/src/components/automation/types";
import type { DetectorModel } from "@/src/model/system";
import { DeviceRow } from "../DeviceRow";

export function DetectorRow({
  detector,
  hubId,
  topology,
  automationDocument,
  automationSaving,
  onAutomationDocumentChange,
}: {
  readonly detector: DetectorModel;
  readonly hubId: string;
  readonly topology: AutomationTopology;
  readonly automationDocument: AutomationDocument;
  readonly automationSaving: boolean;
  readonly onAutomationDocumentChange: (document: AutomationDocument) => void;
}) {
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
    >
      <AutomationEditor
        hubId={hubId}
        detectorId={detector.id}
        topology={topology}
        document={automationDocument}
        disabled={automationSaving}
        onDocumentChange={onAutomationDocumentChange}
      />
    </DeviceRow>
  );
}
