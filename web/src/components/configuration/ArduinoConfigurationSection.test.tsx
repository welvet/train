import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { ConfigurationSnapshot } from "@/src/api/train-api-client";
import { ConfigurationPage } from "./ConfigurationPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

it("edits and saves the complete Arduino document independently", async () => {
  let configuration = configurationSnapshot();
  const fetchMock = vi.fn().mockImplementation(
    (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "PUT") {
        const update = JSON.parse(String(init.body));
        configuration = {
          ...configuration,
          documents: {
            ...configuration.documents,
            arduinos: {
              ...configuration.documents.arduinos!,
              modified_at: 2000,
              value: update.documents.arduinos.value,
            },
          },
        };
      }
      return Promise.resolve(new Response(JSON.stringify(configuration), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  renderPage();

  expect(await screen.findByDisplayValue("hub_1")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Hub ID"), {
    target: { value: "yard_hub" },
  });
  fireEvent.click(screen.getByRole("button", {
    name: "Save Arduino configuration and restart",
  }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  const body = JSON.parse(fetchMock.mock.calls[1][1].body);
  expect(Object.keys(body.documents)).toEqual(["arduinos"]);
  expect(body.documents.arduinos.base_modified_at).toBe(1000);
  expect(body.documents.arduinos.value.devices.arduino_1).toMatchObject({
    hub_id: "yard_hub",
    port: "/dev/test",
    backend_host: "127.0.0.1",
  });
  expect(body.documents.arduinos.value.devices.arduino_1).not.toHaveProperty(
    "wifi_password",
  );
});

it("keeps train editing available against a trains-only rollback backend", async () => {
  const configuration = configurationSnapshot();
  delete configuration.documents.arduinos;
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
    new Response(JSON.stringify(configuration), { status: 200 }),
  ));
  renderPage();

  expect(await screen.findByDisplayValue("express")).toBeInTheDocument();
  expect(screen.getByText("Arduino editing unavailable")).toBeInTheDocument();
});

it("disables component creation when every supported pin is assigned", async () => {
  const configuration = configurationSnapshot();
  const device = configuration.documents.arduinos!.value.devices.arduino_1;
  device.switches = [2, 3, 4, 5].map((pin, index) => ({
    id: `S${index + 1}`,
    pin,
    straight: 60,
    diverge: 120,
  }));
  device.readers = [6, 7, 8, 9, 10].map((ss_pin, index) => ({
    id: `D${index + 1}`,
    ss_pin,
    read_timeout_ms: 250,
    removal_delay_ms: 750,
  }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
    new Response(JSON.stringify(configuration), { status: 200 }),
  ));
  renderPage();

  expect(
    await screen.findByRole("button", { name: "Add switch" }),
  ).toBeDisabled();
  expect(screen.getByRole("button", { name: "Add reader" })).toBeDisabled();
});

it("uses D10 when it is the final available component pin", async () => {
  const configuration = configurationSnapshot();
  const device = configuration.documents.arduinos!.value.devices.arduino_1;
  device.switches = [2, 3, 4, 5].map((pin, index) => ({
    id: `S${index + 1}`,
    pin,
    straight: 60,
    diverge: 120,
  }));
  device.readers = [6, 7, 8, 9].map((ss_pin, index) => ({
    id: `D${index + 1}`,
    ss_pin,
    read_timeout_ms: 250,
    removal_delay_ms: 750,
  }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
    new Response(JSON.stringify(configuration), { status: 200 }),
  ));
  renderPage();

  const addSwitch = await screen.findByRole("button", { name: "Add switch" });
  expect(addSwitch).toBeEnabled();
  fireEvent.click(addSwitch);

  expect(screen.getAllByLabelText("Pin").at(-1)).toHaveValue("10");
  expect(screen.getByRole("button", { name: "Add reader" })).toBeDisabled();
});

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <MantineProvider>
      <QueryClientProvider client={queryClient}>
        <ConfigurationPage />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

function configurationSnapshot(): ConfigurationSnapshot {
  return {
    version: 1,
    documents: {
      trains: {
        modified_at: 1000,
        restart_required: true,
        value: {
          trains: [{
            id: "express",
            lego_hub_id: "express-hub",
            ble_address: "AA:BB",
            tag_ids: ["04:AB"],
          }],
        },
      },
      arduinos: {
        modified_at: 1000,
        restart_required: true,
        value: {
          devices: {
            arduino_1: {
              port: "/dev/test",
              fqbn: "arduino:renesas_uno:unor4wifi",
              baudrate: 9600,
              hub_id: "hub_1",
              backend_host: "127.0.0.1",
              backend_port: 9000,
              servo_settle_ms: 500,
              reconnect_ms: 2000,
              event_logger_enabled: false,
              switches: [{ id: "S1", pin: 9, straight: 60, diverge: 120 }],
              readers: [{
                id: "D1",
                ss_pin: 4,
                read_timeout_ms: 250,
                removal_delay_ms: 750,
              }],
            },
          },
        },
      },
    },
  };
}
