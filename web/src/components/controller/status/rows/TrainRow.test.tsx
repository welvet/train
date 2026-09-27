import { fireEvent, render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";

import type { TrainModel } from "@/src/model/system";
import { useSystem } from "@/src/state/SystemProvider";
import { TrainRow } from "./TrainRow";

vi.mock("@/src/state/SystemProvider", () => ({ useSystem: vi.fn() }));

const train: TrainModel = {
  id: "express",
  speed: 50,
  legoHub: {
    id: "express-hub",
    connected: true,
    batteryPct: 80,
    voltage: 7.8,
  },
};

it("shuts down a connected train", () => {
  const shutdownTrain = vi.fn(async () => undefined);
  vi.mocked(useSystem).mockReturnValue({
    actions: {
      setTrainSpeed: vi.fn(),
      shutdownTrain,
      setSwitchPosition: vi.fn(),
      setAutomationHalted: vi.fn(),
      replaceAutomation: vi.fn(),
      refresh: vi.fn(),
    },
    connection: "online",
    pendingResources: new Set(),
    model: null,
    refreshing: false,
    error: null,
    liveUpdateError: null,
    commandError: null,
  });

  render(
    <MantineProvider>
      <TrainRow train={train} />
    </MantineProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Shut down express" }));

  expect(shutdownTrain).toHaveBeenCalledWith("express");
});

it("disables shutdown when the LEGO hub is disconnected", () => {
  vi.mocked(useSystem).mockReturnValue({
    actions: {
      setTrainSpeed: vi.fn(),
      shutdownTrain: vi.fn(),
      setSwitchPosition: vi.fn(),
      setAutomationHalted: vi.fn(),
      replaceAutomation: vi.fn(),
      refresh: vi.fn(),
    },
    connection: "online",
    pendingResources: new Set(),
    model: null,
    refreshing: false,
    error: null,
    liveUpdateError: null,
    commandError: null,
  });

  render(
    <MantineProvider>
      <TrainRow
        train={{ ...train, legoHub: { ...train.legoHub!, connected: false } }}
      />
    </MantineProvider>,
  );

  expect(
    screen.getByRole("button", { name: "Shut down express" }),
  ).toBeDisabled();
});
