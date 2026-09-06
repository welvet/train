import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { StateEnvelope } from "@/src/api/train-api-client";
import type { AutomationDocument } from "@/src/components/automation/types";
import { AppProviders } from "@/src/components/shell/AppProviders";
import { MainController } from "./MainController";

it("renders the full device hierarchy from one state request", async () => {
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          input.toString().endsWith("/api/events")
            ? { accepted: true }
            : stateEnvelope(),
        ),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    ),
  );
  vi.stubGlobal("fetch", fetchMock);

  render(
    <AppProviders>
      <MainController />
    </AppProviders>,
  );

  expect(await screen.findByText("express")).toBeInTheDocument();
  expect(screen.getByText("express-hub")).toBeInTheDocument();
  expect(screen.getByText("yard")).toBeInTheDocument();
  expect(screen.getByText("S1")).toBeInTheDocument();
  expect(screen.getByText("D1")).toBeInTheDocument();
  expect(screen.getByText("Unknown tag")).toBeInTheDocument();
  expect(screen.getByText("DE:AD:BE:EF")).toBeInTheDocument();
  expect(screen.getAllByText("Automation")).toHaveLength(3);
  expect(
    screen.getByRole("button", { name: "Create automation for yard / D1" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Create automation for yard / D2" }),
  ).toBeInTheDocument();
  for (const speed of [-100, -80, -50, -30, 30, 50, 80, 100]) {
    expect(
      screen.getByRole("button", { name: `Set express speed to ${speed}%` }),
    ).toBeInTheDocument();
  }
  expect(screen.getByRole("button", { name: "Stop express" })).toHaveTextContent(
    "STOP",
  );
  expect(
    screen.getByRole("button", { name: "Set switch S1 on yard to straight" }),
  ).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);

  fireEvent.click(screen.getByRole("button", { name: "Set express speed to 50%" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/events",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          type: "set_train_speed",
          data: { train_id: "express", speed: 50 },
        }),
      }),
    ),
  );

  vi.unstubAllGlobals();
});

it("loads and saves the backend automation document", async () => {
  let envelope = stateEnvelope();
  envelope.automation.document = {
    version: 1,
    rules: [
      {
        id: "stop_at_yard",
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
  const fetchMock = vi.fn().mockImplementation(
    (input: RequestInfo | URL, init?: RequestInit) => {
      if (input.toString().endsWith("/api/automation")) {
        const document = JSON.parse(String(init?.body));
        envelope = {
          ...envelope,
          snapshot_at: envelope.snapshot_at + 1,
          automation: { ...envelope.automation, document },
        };
        return Promise.resolve(
          new Response(
            JSON.stringify({
              automation: {
                document,
                eligible_train_ids: envelope.automation.eligible_train_ids,
                paused: false,
                statuses: [],
              },
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify(envelope), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    },
  );
  vi.stubGlobal("fetch", fetchMock);

  render(
    <AppProviders>
      <MainController />
    </AppProviders>,
  );

  const speedInput = await screen.findByRole("textbox", { name: "Train speed (%)" });
  expect(screen.getByText("Saved")).toBeInTheDocument();
  fireEvent.change(speedInput, { target: { value: "50" } });
  expect(screen.getByText("Unsaved")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Save automation" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/automation",
      expect.objectContaining({
        method: "PUT",
        body: expect.stringContaining('"speed":50'),
      }),
    ),
  );
  await waitFor(() => expect(screen.getByText("Saved")).toBeInTheDocument());

  vi.unstubAllGlobals();
});

it("disables automation editing while a save is in flight", async () => {
  let envelope = stateEnvelope();
  let resolveSave: ((response: Response) => void) | undefined;
  const saveResponse = new Promise<Response>((resolve) => {
    resolveSave = resolve;
  });
  const fetchMock = vi.fn().mockImplementation(
    (input: RequestInfo | URL, init?: RequestInit) => {
      if (input.toString().endsWith("/api/automation")) {
        const document = JSON.parse(String(init?.body));
        envelope = {
          ...envelope,
          snapshot_at: envelope.snapshot_at + 1,
          automation: { ...envelope.automation, document },
        };
        return saveResponse;
      }
      return Promise.resolve(
        new Response(JSON.stringify(envelope), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    },
  );
  vi.stubGlobal("fetch", fetchMock);

  render(
    <AppProviders>
      <MainController />
    </AppProviders>,
  );

  fireEvent.click(
    await screen.findByRole("button", { name: "Create automation for yard / D1" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Add speed step" }));
  fireEvent.click(screen.getByRole("button", { name: "Save automation" }));
  expect(screen.getByRole("button", { name: "Run when express arrives" })).toBeDisabled();

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/automation",
      expect.objectContaining({ method: "PUT" }),
    ),
  );

  resolveSave?.(
    new Response(
      JSON.stringify({
        automation: {
          document: envelope.automation.document,
          eligible_train_ids: envelope.automation.eligible_train_ids,
          paused: false,
          statuses: [],
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );

  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Run when express arrives" })).toBeEnabled(),
  );
  await waitFor(() => expect(screen.getByText("Saved")).toBeInTheDocument());

  vi.unstubAllGlobals();
});

it("keeps a dormant backend rule off when creating an active rule", async () => {
  const envelope = stateEnvelope();
  envelope.automation.document = {
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
  };
  const fetchMock = vi.fn().mockImplementation(
    (input: RequestInfo | URL, init?: RequestInit) =>
      Promise.resolve(
        new Response(
          input.toString().endsWith("/api/automation")
            ? JSON.stringify({
                automation: {
                  document: JSON.parse(String(init?.body)),
                  eligible_train_ids: envelope.automation.eligible_train_ids,
                  paused: false,
                  statuses: [],
                },
              })
            : JSON.stringify(envelope),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
  );
  vi.stubGlobal("fetch", fetchMock);

  render(
    <AppProviders>
      <MainController />
    </AppProviders>,
  );

  expect(await screen.findByText("Saved")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Create automation for yard / D1" }));
  fireEvent.click(screen.getByRole("button", { name: "Add speed step" }));
  expect(screen.getByText("Unsaved")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Save automation" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/automation",
      expect.objectContaining({ method: "PUT" }),
    ),
  );
  const saveCall = fetchMock.mock.calls.find(([input]) =>
    input.toString().endsWith("/api/automation"),
  );
  const savedDocument = JSON.parse(String(saveCall?.[1]?.body)) as AutomationDocument;
  expect(savedDocument.rules.map((rule) => rule.enabled)).toEqual([false, true]);

  vi.unstubAllGlobals();
});

function stateEnvelope(): StateEnvelope {
  return {
    version: 4,
    snapshot_at: Date.now() / 1000,
    automation: {
      document: { version: 1, rules: [] },
      eligible_train_ids: ["express"],
      paused: false,
      statuses: [],
    },
    state: {
      revision: 4,
      updated_at: Date.now() / 1000,
      running: true,
      automation: { halted: false },
      trains: {
        express: {
          train_id: "express",
          lego_hub_id: "express-hub",
          speed: 20,
        },
      },
      lego_hubs: {
        "express-hub": {
          hub_id: "express-hub",
          train_id: "express",
          connected: true,
          battery_pct: 80,
          voltage: 7.6,
        },
      },
      arduino_hubs: {
        yard: {
          hub_id: "yard",
          device_id: "arduino-1",
          connected: true,
          switches: { S1: { switch_id: "S1", angle: 90 } },
          detectors: {
            D1: {
              detector_id: "D1",
              available: true,
              triggered: false,
              train_id: null,
              unknown_tag_id: null,
            },
            D2: {
              detector_id: "D2",
              available: true,
              triggered: true,
              train_id: null,
              unknown_tag_id: "DE:AD:BE:EF",
            },
          },
        },
      },
    },
  };
}
