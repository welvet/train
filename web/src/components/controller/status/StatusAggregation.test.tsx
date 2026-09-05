import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  expect(screen.getByText("Unsaved")).toBeInTheDocument();

  rerender(statusAggregation(externalDocument, onReplaceAutomation));

  expect(screen.getByText("Changed elsewhere")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save automation" })).toBeDisabled();
  fireEvent.click(
    screen.getByRole("button", { name: "Reload active automation" }),
  );
  expect(screen.getByRole("button", { name: "Run when express arrives" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(onReplaceAutomation).not.toHaveBeenCalled();
});

it("keeps a new empty rule as an unfinished choice until a step is added", () => {
  const onReplaceAutomation = vi.fn();
  renderStatus(emptyDocument, onReplaceAutomation);

  fireEvent.click(
    screen.getByRole("button", { name: "Create automation for yard / D1" }),
  );

  expect(screen.getByText("Unsaved")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save automation" })).toBeDisabled();
  expect(
    screen.queryByText("Automation draft cannot be saved"),
  ).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Add speed step" }));

  expect(screen.getByRole("button", { name: "Save automation" })).toBeEnabled();
});

it("removes only invalid dormant rules from the document-level cleanup", async () => {
  const invalidDormantRule: AutomationDocument["rules"][number] = {
    id: "missing_switch",
    enabled: false,
    root: {
      type: "train_detected",
      hub_id: "yard",
      detector_id: "D1",
      train_id: "express",
      children: [
        {
          type: "set_switch",
          hub_id: "yard",
          switch_id: "gone",
          position: "straight",
          children: [],
        },
      ],
    },
  };
  const validDormantRule: AutomationDocument["rules"][number] = {
    id: "valid_stop",
    enabled: false,
    root: {
      type: "train_detected",
      hub_id: "yard",
      detector_id: "D1",
      train_id: "express",
      children: [{ type: "set_train_speed", speed: 0, children: [] }],
    },
  };
  const onReplaceAutomation = vi.fn(
    async (document: AutomationDocument) => document,
  );
  renderStatus(
    { version: 1, rules: [validDormantRule, invalidDormantRule] },
    onReplaceAutomation,
  );

  fireEvent.click(
    screen.getByRole("button", {
      name: "Remove dormant rules that no longer match the railway",
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Save automation" }));

  await waitFor(() => expect(onReplaceAutomation).toHaveBeenCalledTimes(1));
  expect(onReplaceAutomation).toHaveBeenCalledWith({
    version: 1,
    rules: [validDormantRule],
  });
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
