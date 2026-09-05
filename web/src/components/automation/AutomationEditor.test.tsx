import { fireEvent, render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import { useState } from "react";

import { AutomationEditor } from "./AutomationEditor";
import type { AutomationDocument } from "./types";

const topology = {
  trainIds: ["express", "freight"],
  switches: [{ hubId: "yard", switchId: "S1" }],
  detectors: [
    { hubId: "yard", detectorId: "D1" },
    { hubId: "yard", detectorId: "D2" },
  ],
};

function renderEditor() {
  function ControlledEditor() {
    const [document, setDocument] = useState<AutomationDocument>({ version: 1, rules: [] });
    return (
      <AutomationEditor
        hubId="yard"
        detectorId="D1"
        topology={topology}
        document={document}
        onDocumentChange={setDocument}
      />
    );
  }
  return render(
    <MantineProvider>
      <ControlledEditor />
    </MantineProvider>,
  );
}

it("builds a local automation and generates its JSON", () => {
  renderEditor();

  expect(
    screen.getByRole("group", { name: "Automation for yard / D1" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));
  expect(screen.getByLabelText("Rule name")).toHaveValue("yard_d1_express");
  expect(screen.getByText("Set train speed")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "View automation JSON for yard / D1" }));
  expect((screen.getByLabelText("Complete automation JSON for yard / D1") as HTMLTextAreaElement).value).toContain(
    '"detector_id": "D1"',
  );
});

it("parses nested JSON into the visual editor", () => {
  renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "View automation JSON for yard / D1" }));

  fireEvent.change(screen.getByLabelText("Complete automation JSON for yard / D1"), {
    target: {
      value: JSON.stringify({
        version: 1,
        rules: [
          {
            id: "fifth_arrival",
            enabled: true,
            root: {
              type: "train_detected",
              hub_id: "yard",
              detector_id: "D1",
              train_id: "freight",
              children: [
                {
                  type: "on_count",
                  count: 5,
                  mode: "once",
                  children: [
                    {
                      type: "wait",
                      seconds: 20,
                      children: [
                        {
                          type: "set_switch",
                          hub_id: "yard",
                          switch_id: "S1",
                          position: "diverge",
                          children: [],
                        },
                      ],
                    },
                  ],
                },
              ],
            },
          },
        ],
      }),
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "Apply JSON" }));

  expect(screen.getByLabelText("Rule name")).toHaveValue("fifth_arrival");
  expect(screen.getByText("Count detections")).toBeInTheDocument();
  expect(screen.getByLabelText("Delay")).toHaveValue("20");
  expect(screen.getByText("Move switch")).toBeInTheDocument();
  expect(screen.getByText("JSON applied to the visual draft")).toBeInTheDocument();
});

it("updates a nested control step without losing the surrounding tree", () => {
  renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "View automation JSON for yard / D1" }));
  fireEvent.change(screen.getByLabelText("Complete automation JSON for yard / D1"), {
    target: {
      value: JSON.stringify({
        version: 1,
        rules: [
          {
            id: "delayed_arrival",
            enabled: true,
            root: {
              type: "train_detected",
              hub_id: "yard",
              detector_id: "D1",
              train_id: "express",
              children: [
                {
                  type: "on_count",
                  count: 3,
                  mode: "repeat",
                  children: [
                    {
                      type: "wait",
                      seconds: 2,
                      children: [
                        { type: "set_train_speed", speed: 40, children: [] },
                      ],
                    },
                  ],
                },
              ],
            },
          },
        ],
      }),
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "Apply JSON" }));

  fireEvent.change(screen.getByLabelText("Delay"), { target: { value: "7" } });
  expect(screen.getByText("JSON snapshot is out of date")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Regenerate" }));

  const exported = JSON.parse(
    (screen.getByLabelText("Complete automation JSON for yard / D1") as HTMLTextAreaElement)
      .value,
  );
  expect(exported.rules[0].root.children[0]).toMatchObject({
    type: "on_count",
    count: 3,
    mode: "repeat",
    children: [
      {
        type: "wait",
        seconds: 7,
        children: [{ type: "set_train_speed", speed: 40, children: [] }],
      },
    ],
  });
});

it("does not let a stale JSON snapshot overwrite visual edits", () => {
  renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));
  fireEvent.click(screen.getByRole("button", { name: "View automation JSON for yard / D1" }));
  fireEvent.change(screen.getByLabelText("Rule name"), {
    target: { value: "updated_in_visual_editor" },
  });

  expect(screen.getByText("JSON snapshot is out of date")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Apply JSON" })).toBeDisabled();
});

it("keeps only one rule enabled for the same detector and train", () => {
  renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));
  fireEvent.click(
    screen.getByRole("button", { name: "Add alternative automation for yard / D1" }),
  );

  const trainSelectors = screen.getAllByLabelText("When this train arrives");
  fireEvent.change(trainSelectors[1], { target: { value: "express" } });
  fireEvent.click(screen.getByRole("button", { name: "View automation JSON for yard / D1" }));

  const exported = JSON.parse(
    (screen.getByLabelText("Complete automation JSON for yard / D1") as HTMLTextAreaElement)
      .value,
  );
  expect(exported.rules.map((rule: AutomationDocument["rules"][number]) => rule.enabled)).toEqual([
    false,
    true,
  ]);
});

it("does not export an invalid visual draft", () => {
  renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));
  fireEvent.change(screen.getByLabelText("Rule name"), { target: { value: "" } });

  expect(screen.getByText("Rule name is required")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "View automation JSON for yard / D1" })).toBeDisabled();
  expect(
    screen.getByText("Rule 1 id must be a non-empty string."),
  ).toBeInTheDocument();
});

it("does not export a draft that references removed topology", () => {
  render(
    <MantineProvider>
      <AutomationEditor
        hubId="yard"
        detectorId="D1"
        topology={topology}
        document={{
          version: 1,
          rules: [
            {
              id: "removed_switch",
              enabled: true,
              root: {
                type: "train_detected",
                hub_id: "yard",
                detector_id: "D1",
                train_id: "express",
                children: [
                  {
                    type: "set_switch",
                    hub_id: "yard",
                    switch_id: "missing",
                    position: "straight",
                    children: [],
                  },
                ],
              },
            },
          ],
        }}
        onDocumentChange={() => undefined}
      />
    </MantineProvider>,
  );

  expect(
    screen.getByRole("button", { name: "View automation JSON for yard / D1" }),
  ).toBeDisabled();
  expect(screen.getByText("Switch yard / missing is not configured.")).toBeInTheDocument();
});
