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

it("builds a rule with numeric speed input", () => {
  const getDocument = renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));

  fireEvent.click(screen.getByRole("button", { name: "Add speed step" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Train speed (%)" }), {
    target: { value: "37" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Add wait step" }));
  fireEvent.click(screen.getByRole("button", { name: "Wait 5 seconds" }));
  fireEvent.click(screen.getAllByRole("button", { name: "Add switch step" })[0]);
  fireEvent.click(screen.getByRole("button", { name: "Flip switch position" }));

  expect(getDocument().rules[0].root.children).toMatchObject([
    { type: "set_train_speed", speed: 37 },
    {
      type: "wait",
      seconds: 5,
      children: [
        { type: "set_switch", switch_id: "S1", position: "flip" },
      ],
    },
  ]);
});

it("upgrades version 1 when adding a count branch with two fixed outcomes", () => {
  const getDocument = renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));
  fireEvent.click(screen.getByRole("button", { name: "Add count branch step" }));

  expect(screen.getByText("Every 5th time")).toBeVisible();
  expect(screen.getByText("All other times")).toBeVisible();
  const matchSteps = screen.getByRole("group", { name: "Steps every configured count" });
  const otherwiseSteps = screen.getByRole("group", { name: "Steps all other times" });
  fireEvent.click(within(matchSteps).getByRole("button", { name: "Add speed step" }));
  fireEvent.click(within(otherwiseSteps).getByRole("button", { name: "Add speed step" }));

  expect(getDocument()).toMatchObject({
    version: 2,
    rules: [
      {
        root: {
          children: [
            {
              type: "if_count",
              count: 5,
              children: [
                { type: "branch", when: "match", children: [{ type: "set_train_speed" }] },
                {
                  type: "branch",
                  when: "otherwise",
                  children: [{ type: "set_train_speed" }],
                },
              ],
            },
          ],
        },
      },
    ],
  });
});

it("preserves document versions during ordinary edits", () => {
  const v1Document: AutomationDocument = {
    version: 1,
    rules: [
      {
        id: "v1",
        enabled: true,
        root: {
          type: "train_detected",
          hub_id: "yard",
          detector_id: "D1",
          train_id: "express",
          children: [{ type: "set_train_speed", speed: 10, children: [] }],
        },
      },
    ],
  };
  const getV1 = renderEditor(v1Document);
  fireEvent.change(screen.getByRole("textbox", { name: "Train speed (%)" }), {
    target: { value: "11" },
  });
  expect(getV1().version).toBe(1);
});

it("never downgrades a version 2 document during ordinary edits", () => {
  const v2Document: AutomationDocument = {
    version: 2,
    rules: [
      {
        id: "v2",
        enabled: true,
        root: {
          type: "train_detected",
          hub_id: "yard",
          detector_id: "D1",
          train_id: "express",
          children: [{ type: "set_train_speed", speed: 10, children: [] }],
        },
      },
    ],
  };
  const getV2 = renderEditor(v2Document);
  fireEvent.change(screen.getByRole("textbox", { name: "Train speed (%)" }), {
    target: { value: "12" },
  });
  expect(getV2().version).toBe(2);
});

it("keeps version 2 after the last count branch is removed", () => {
  const getDocument = renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));
  fireEvent.click(screen.getByRole("button", { name: "Add count branch step" }));
  fireEvent.click(screen.getByRole("button", { name: "Remove Count branch step 1" }));

  expect(getDocument()).toMatchObject({ version: 2, rules: [{ root: { children: [] } }] });
});

it("accepts every valid speed including reverse, stop, and the boundaries", () => {
  const getDocument = renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));
  fireEvent.click(screen.getByRole("button", { name: "Add speed step" }));

  const speedInput = screen.getByRole("textbox", { name: "Train speed (%)" });
  for (const speed of [-100, -73, 0, 42, 100]) {
    fireEvent.change(speedInput, { target: { value: String(speed) } });
    expect(getDocument().rules[0].root.children[0]).toMatchObject({
      type: "set_train_speed",
      speed,
    });
  }
});

it("allows clearing numeric inputs before entering a new speed or count", () => {
  const getDocument = renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));
  fireEvent.click(screen.getByRole("button", { name: "Add speed step" }));
  fireEvent.click(screen.getByRole("button", { name: "Add count step" }));

  const speedInput = screen.getByRole("textbox", { name: "Train speed (%)" });
  fireEvent.change(speedInput, { target: { value: "" } });
  expect(speedInput).toHaveValue("");
  expect(screen.getByText("Enter a whole number from -100 to 100")).toBeVisible();
  fireEvent.change(speedInput, { target: { value: "-73" } });

  const countInput = screen.getByRole("textbox", { name: "Detection count" });
  fireEvent.change(countInput, { target: { value: "" } });
  expect(countInput).toHaveValue("");
  expect(screen.getByText("Enter a positive whole number")).toBeVisible();
  fireEvent.change(countInput, { target: { value: "17" } });

  expect(getDocument().rules[0].root.children).toMatchObject([
    { type: "set_train_speed", speed: -73 },
    { type: "on_count", count: 17 },
  ]);
});

it("rejects invalid speed and repeat count values", () => {
  const getDocument = renderEditor();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));
  fireEvent.click(screen.getByRole("button", { name: "Add speed step" }));
  fireEvent.click(screen.getByRole("button", { name: "Add count step" }));

  const speedInput = screen.getByRole("textbox", { name: "Train speed (%)" });
  const countInput = screen.getByRole("textbox", { name: "Detection count" });

  fireEvent.change(speedInput, { target: { value: "101" } });
  expect(screen.getByText("Speed must be from -100 to 100")).toBeVisible();
  fireEvent.blur(speedInput);
  expect(speedInput).toHaveValue("0");
  fireEvent.change(speedInput, { target: { value: "1.5" } });
  expect(screen.getByText("Enter a whole number from -100 to 100")).toBeVisible();
  fireEvent.blur(speedInput);
  fireEvent.change(countInput, { target: { value: "0" } });
  expect(screen.getByText("Detection count must be at least 1")).toBeVisible();
  fireEvent.blur(countInput);
  expect(countInput).toHaveValue("2");
  fireEvent.change(countInput, { target: { value: "2.5" } });
  expect(screen.getByText("Enter a positive whole number")).toBeVisible();
  fireEvent.blur(countInput);

  const [speedNode, countNode] = getDocument().rules[0].root.children;
  expect(speedNode).toMatchObject({ type: "set_train_speed", speed: 0 });
  expect(countNode).toMatchObject({ type: "on_count", count: 2 });

  fireEvent.change(countInput, { target: { value: "17" } });
  expect(getDocument().rules[0].root.children[1]).toMatchObject({
    type: "on_count",
    count: 17,
  });
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
  expect(screen.queryByRole("button", { name: "Run once" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Repeat forever" })).not.toBeInTheDocument();
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
