import { fireEvent, render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";

import type { AutomationDocument } from "@/src/components/automation/types";
import type { SystemModel } from "@/src/model/system";
import { StatusAggregation } from "./StatusAggregation";

vi.mock("./rows/TrainRow", () => ({ TrainRow: () => null }));

const emptyDocument: AutomationDocument = { version: 1, rules: [] };
const externalDocument: AutomationDocument = {
  version: 1,
  rules: [
    {
      id: "external_rule",
      enabled: true,
      root: {
        type: "train_detected",
        hub_id: "yard",
        detector_id: "D1",
        train_id: "express",
        children: [{ type: "set_train_speed", speed: 0, children: [] }],
      },
    },
  ],
};

it("does not let a local draft overwrite an external automation update", () => {
  const onReplaceAutomation = vi.fn();
  const { rerender } = renderStatus(emptyDocument, onReplaceAutomation);

  fireEvent.click(
    screen.getByRole("button", { name: "Create automation for yard / D1" }),
  );
  expect(screen.getByText("Unsaved changes")).toBeInTheDocument();

  rerender(statusAggregation(externalDocument, onReplaceAutomation));

  expect(screen.getByText("Changed elsewhere")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save automation" })).toBeDisabled();
  fireEvent.click(
    screen.getByRole("button", { name: "Reload active automation" }),
  );
  expect(screen.getByLabelText("Rule name")).toHaveValue("external_rule");
  expect(onReplaceAutomation).not.toHaveBeenCalled();
});

function renderStatus(
  document: AutomationDocument,
  onReplaceAutomation: (
    document: AutomationDocument,
  ) => Promise<AutomationDocument>,
) {
  return render(statusAggregation(document, onReplaceAutomation));
}

function statusAggregation(
  document: AutomationDocument,
  onReplaceAutomation: (
    document: AutomationDocument,
  ) => Promise<AutomationDocument>,
) {
  return (
    <MantineProvider>
      <StatusAggregation
        system={systemModel(document)}
        automationSaving={false}
        onReplaceAutomation={onReplaceAutomation}
      />
    </MantineProvider>
  );
}

function systemModel(automationDocument: AutomationDocument): SystemModel {
  return {
    revision: 1,
    updatedAt: 1_000,
    running: true,
    automationHalted: false,
    automationDocument,
    trains: [{ id: "express", speed: 0, legoHub: null }],
    arduinoHubs: [
      {
        id: "yard",
        deviceId: "arduino-1",
        connected: true,
        switches: [],
        detectors: [
          {
            id: "D1",
            available: true,
            triggered: false,
            trainId: null,
            unknownTagId: null,
          },
        ],
      },
    ],
  };
}
