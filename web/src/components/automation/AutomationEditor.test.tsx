import { fireEvent, render, screen, within } from "@testing-library/react";
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

function renderEditor(
  initial: AutomationDocument = { version: 1, rules: [] },
  editorTopology = topology,
) {
  let latest = initial;

  function ControlledEditor() {
    const [document, setDocument] = useState<AutomationDocument>(initial);
    return (
      <AutomationEditor
        hubId="yard"
        detectorId="D1"
        topology={editorTopology}
        document={document}
        onDocumentChange={(next) => {
          latest = next;
          setDocument(next);
        }}
      />
    );
  }

  render(
    <MantineProvider>
      <ControlledEditor />
    </MantineProvider>,
  );
  return () => latest;
}

it("creates an always-on rule with a generated id", () => {
  const getDocument = renderEditor();

  expect(screen.queryByText("⚡ On")).not.toBeInTheDocument();
  expect(screen.queryByText("🪄")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));

  expect(screen.getByText("⚡ On")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Run when express arrives" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.queryByRole("button", { name: "Stop train" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add speed step" })).toBeVisible();
  expect(screen.queryByText("Needs a fix")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Rule name")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Enabled")).not.toBeInTheDocument();
  expect(screen.queryByText("View JSON")).not.toBeInTheDocument();
  expect(getDocument().rules[0]).toMatchObject({
    id: "yard_d1_express",
    enabled: true,
    root: { train_id: "express", children: [] },
  });
});

it("explains that automation needs a tagged train", () => {
  renderEditor(undefined, { ...topology, trainIds: [] });

  expect(
    screen.getByRole("button", { name: "Create automation for yard / D1" }),
  ).toBeDisabled();
  expect(screen.getByText("Add a tag to a train first")).toBeVisible();
});

it("builds a rule through compact picture controls", () => {
  const getDocument = renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));

  fireEvent.click(screen.getByRole("button", { name: "Add speed step" }));
  fireEvent.click(screen.getByRole("button", { name: "Set train speed to 50%" }));
  fireEvent.click(screen.getByRole("button", { name: "Add wait step" }));
  fireEvent.click(screen.getByRole("button", { name: "Wait 5 seconds" }));
  fireEvent.click(screen.getAllByRole("button", { name: "Add switch step" })[0]);
  fireEvent.click(screen.getByRole("button", { name: "Set switch to turn" }));

  expect(getDocument().rules[0].root.children).toMatchObject([
    { type: "set_train_speed", speed: 50 },
    {
      type: "wait",
      seconds: 5,
      children: [
        { type: "set_switch", switch_id: "S1", position: "diverge" },
      ],
    },
  ]);
});

it("starts every nested action list empty and lets it return to empty", () => {
  const getDocument = renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));
  fireEvent.click(screen.getByRole("button", { name: "Add wait step" }));
  fireEvent.click(screen.getAllByRole("button", { name: "Add count step" }).at(-1)!);

  expect(getDocument().rules[0].root.children).toMatchObject([
    { type: "wait", children: [] },
    { type: "on_count", children: [] },
  ]);
  expect(screen.queryByRole("button", { name: "Stop train" })).not.toBeInTheDocument();

  const waitSteps = screen.getByRole("group", { name: "Steps after Wait step 1" });
  fireEvent.click(within(waitSteps).getByRole("button", { name: "Add speed step" }));
  fireEvent.click(screen.getByRole("button", { name: "Remove Speed step 1" }));
  expect(getDocument().rules[0].root.children[0]).toMatchObject({
    type: "wait",
    children: [],
  });
});

it("can return to an empty list after choosing the wrong first step", () => {
  const getDocument = renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));
  fireEvent.click(screen.getByRole("button", { name: "Add speed step" }));
  fireEvent.click(screen.getByRole("button", { name: "Remove Speed step 1" }));

  expect(getDocument().rules[0].root.children).toEqual([]);
  expect(screen.getByRole("button", { name: "Add speed step" })).toBeVisible();
});

it("regenerates the hidden rule id when the train changes", () => {
  const getDocument = renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));
  fireEvent.click(screen.getByRole("button", { name: "Run when freight arrives" }));

  expect(getDocument().rules[0]).toMatchObject({
    id: "yard_d1_freight",
    enabled: true,
    root: { train_id: "freight" },
  });
});

it("offers one always-on rule per train", () => {
  const getDocument = renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));
  fireEvent.click(
    screen.getByRole("button", { name: "Add automation for another train at yard / D1" }),
  );

  expect(getDocument().rules.map((rule) => [rule.root.train_id, rule.enabled])).toEqual([
    ["express", true],
    ["freight", true],
  ]);
  expect(
    screen.getByRole("button", { name: "Add automation for another train at yard / D1" }),
  ).toBeDisabled();
});

it("keeps a dormant legacy rule untouched when creating a new rule", () => {
  const getDocument = renderEditor({
    version: 1,
    rules: [
      {
        id: "old_rule",
        enabled: false,
        root: {
          type: "train_detected",
          hub_id: "yard",
          detector_id: "D1",
          train_id: "express",
          children: [{ type: "set_train_speed", speed: 0, children: [] }],
        },
      },
    ],
  });

  expect(screen.getByRole("button", { name: "Create automation for yard / D1" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));
  expect(getDocument().rules.map((rule) => rule.enabled)).toEqual([false, true]);
});

it("shows topology errors without exposing expert JSON controls", () => {
  const getDocument = renderEditor({
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
  });

  expect(screen.getByText("Switch yard / missing is not configured.")).toBeInTheDocument();
  expect(screen.getByLabelText("Choose switch")).toHaveValue("yard\u0000missing");
  expect(screen.getByRole("option", { name: "⚠️ Missing yard / missing" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Choose switch"), {
    target: { value: "yard\u0000S1" },
  });
  expect(getDocument().rules[0].root.children[0]).toMatchObject({
    type: "set_switch",
    hub_id: "yard",
    switch_id: "S1",
  });
  expect(screen.queryByText("Switch yard / missing is not configured.")).not.toBeInTheDocument();
  expect(screen.queryByText("View JSON")).not.toBeInTheDocument();
});


it("distinguishes switches with the same id on different hubs", () => {
  renderEditor(
    {
      version: 1,
      rules: [
        {
          id: "shared_switch_ids",
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
                switch_id: "S1",
                position: "straight",
                children: [],
              },
            ],
          },
        },
      ],
    },
    {
      ...topology,
      switches: [
        { hubId: "yard", switchId: "S1" },
        { hubId: "depot", switchId: "S1" },
      ],
    },
  );

  expect(screen.getByRole("option", { name: "🚦 yard / S1" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "🚦 depot / S1" })).toBeInTheDocument();
});
