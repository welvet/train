import Robot from "@fluentui-emoji/react/flat/robot";
import { Text } from "@mantine/core";

import type { AutomationDocument, AutomationTopology } from "@/src/components/automation/types";
import type { ArduinoHubModel } from "@/src/model/system";
import { DeviceRow } from "../DeviceRow";
import { StatusBadge } from "../StatusBadge";
import { StatusGroup } from "../StatusGroup";
import { DetectorRow } from "./DetectorRow";
import { SwitchRow } from "./SwitchRow";

export function ArduinoHubRow({
  hub,
  topology,
  automationDocument,
  automationSaving,
  onAutomationDocumentChange,
}: {
  readonly hub: ArduinoHubModel;
  readonly topology: AutomationTopology;
  readonly automationDocument: AutomationDocument;
  readonly automationSaving: boolean;
  readonly onAutomationDocumentChange: (document: AutomationDocument) => void;
}) {
  return (
    <DeviceRow
      icon={<Robot width={36} aria-hidden />}
      kind="Arduino hub"
      title={hub.id}
      summary={
        <>
          <StatusBadge connected={hub.connected} />
          {hub.deviceId && (
            <Text size="sm" c="dimmed">
              {hub.deviceId}
            </Text>
          )}
        </>
      }
    >
      <StatusGroup
        title="Switches"
        empty="No switches are configured for this hub."
        isEmpty={hub.switches.length === 0}
        nested
      >
        {hub.switches.map((item) => (
          <SwitchRow key={item.id} hubId={hub.id} connected={hub.connected} item={item} />
        ))}
      </StatusGroup>
      <StatusGroup
        title="Detectors"
        empty="No detectors are configured for this hub."
        isEmpty={hub.detectors.length === 0}
        nested
      >
        {hub.detectors.map((detector) => (
          <DetectorRow
            key={detector.id}
            detector={detector}
            hubId={hub.id}
            topology={topology}
            automationDocument={automationDocument}
            automationSaving={automationSaving}
            onAutomationDocumentChange={onAutomationDocumentChange}
          />
        ))}
      </StatusGroup>
    </DeviceRow>
  );
}
