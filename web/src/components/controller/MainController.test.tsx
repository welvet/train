import { fireEvent, render, screen, waitFor } from "@testing-library/react";

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
  expect(screen.getAllByText("Automation")).toHaveLength(2);
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

function stateEnvelope() {
  return {
    version: 2,
    snapshot_at: Date.now() / 1000,
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
