import { render, screen } from "@testing-library/react";

import { AppProviders } from "@/src/components/shell/AppProviders";
import { MainController } from "./MainController";

it("renders the full device hierarchy from one state request", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(stateEnvelope()), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
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
  expect(
    screen.getByRole("button", { name: "Apply speed for express" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Set switch S1 on yard to straight" }),
  ).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);

  vi.unstubAllGlobals();
});

function stateEnvelope() {
  return {
    version: 1,
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
            },
          },
        },
      },
    },
  };
}
