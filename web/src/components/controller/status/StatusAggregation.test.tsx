import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

it("renders the automation status with its save control below the editors", () => {
  renderStatus(emptyDocument, vi.fn());

  const createAutomation = screen.getByRole("button", {
    name: "Create automation for yard / D1",
  });
  const automationStatus = screen.getByRole("region", {
    name: "Automation save status",
  });
  const saveAutomation = within(automationStatus).getByRole("button", {
    name: "Save automation",
  });

  expect(automationStatus).toHaveTextContent("Automation");
  expect(automationStatus).toHaveTextContent("Saved");
  expect(automationStatus.nextElementSibling).toBeNull();
  expect(
    createAutomation.compareDocumentPosition(saveAutomation) &
      Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
});

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

it("offers only trains the backend marks eligible for automation", () => {
  const onReplaceAutomation = vi.fn();
  renderStatus(emptyDocument, onReplaceAutomation);

  fireEvent.click(
    screen.getByRole("button", { name: "Create automation for yard / D1" }),
  );

  expect(screen.getByRole("button", { name: "Run when express arrives" })).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Run when untagged arrives" }),
  ).not.toBeInTheDocument();
});

it("keeps an empty nested action quiet and unsaveable until it gets a child", () => {
  const onReplaceAutomation = vi.fn();
  renderStatus(emptyDocument, onReplaceAutomation);

  fireEvent.click(
    screen.getByRole("button", { name: "Create automation for yard / D1" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Add count step" }));

  expect(screen.getByRole("button", { name: "Save automation" })).toBeDisabled();
  expect(
    screen.queryByText("Automation draft cannot be saved"),
  ).not.toBeInTheDocument();

  fireEvent.click(screen.getAllByRole("button", { name: "Add speed step" })[0]);
  expect(screen.getByRole("button", { name: "Save automation" })).toBeEnabled();
});

it("keeps both count branches unfinished until each has an action", async () => {
  const onReplaceAutomation = vi.fn(
    async (document: AutomationDocument) => document,
  );
  renderStatus(emptyDocument, onReplaceAutomation);

  fireEvent.click(
    screen.getByRole("button", { name: "Create automation for yard / D1" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Add count branch step" }));

  const save = screen.getByRole("button", { name: "Save automation" });
  expect(save).toBeDisabled();
  expect(screen.queryByText("Automation draft cannot be saved")).not.toBeInTheDocument();

  fireEvent.click(
    within(screen.getByRole("group", { name: "Steps every configured count" }))
      .getByRole("button", { name: "Add speed step" }),
  );
  expect(save).toBeDisabled();

  fireEvent.click(
    within(screen.getByRole("group", { name: "Steps all other times" }))
      .getByRole("button", { name: "Add speed step" }),
  );
  expect(save).toBeEnabled();
  fireEvent.click(save);

  await waitFor(() => expect(onReplaceAutomation).toHaveBeenCalledTimes(1));
  expect(onReplaceAutomation.mock.calls[0][0].version).toBe(2);
});

it("still shows unrelated validation errors on an unfinished rule", () => {
  const document: AutomationDocument = {
    version: 1,
    rules: [
      {
        id: "missing_train",
        enabled: true,
        root: {
          type: "train_detected",
          hub_id: "yard",
          detector_id: "D1",
          train_id: "freight",
          children: [{ type: "set_train_speed", speed: 0, children: [] }],
        },
      },
    ],
  };

  renderStatus(document, vi.fn());
  fireEvent.click(screen.getByRole("button", { name: "Remove Speed step 1" }));

  expect(screen.getByText("Automation draft cannot be saved")).toBeInTheDocument();
  expect(screen.getAllByText("Train freight is not configured.")).toHaveLength(2);
  expect(screen.getByRole("button", { name: "Save automation" })).toBeDisabled();
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
    automationTrainIds: ["express"],
    trains: [
      { id: "express", speed: 0, legoHub: null },
      { id: "untagged", speed: 0, legoHub: null },
    ],
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
