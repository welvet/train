import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { ConfigurationSnapshot } from "@/src/api/train-api-client";
import { ConfigurationPage } from "./ConfigurationPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

it("loads, edits, and saves trains as one configuration update", async () => {
  let configuration = configurationSnapshot();
  const fetchMock = vi.fn().mockImplementation(
    (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "PUT") {
        const update = JSON.parse(String(init.body));
        configuration = {
          version: 1,
          documents: {
            trains: {
              ...configuration.documents.trains,
              modified_at: 2000,
              value: update.documents.trains.value,
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

  expect(await screen.findByDisplayValue("express")).toBeInTheDocument();
  expect(screen.getByText("Saved")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("BLE address"), {
    target: { value: "CC:DD" },
  });
  expect(screen.getByText("Unsaved")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Save configuration" }));

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/configuration",
      expect.objectContaining({ method: "PUT" }),
    ),
  );
  const [, request] = fetchMock.mock.calls.find(
    ([, init]) => init?.method === "PUT",
  )!;
  const body = JSON.parse(String(request.body));
  expect(body).toMatchObject({
    version: 1,
    documents: {
      trains: {
        value: {
          trains: [{ id: "express", ble_address: "CC:DD" }],
        },
      },
    },
  });
  expect(body.documents.trains.modified_at).toBeUndefined();
  await waitFor(() => expect(screen.getByText("Saved")).toBeInTheDocument());
});

it("can add and remove train forms without saving early", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(configurationSnapshot()), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);

  renderPage();

  await screen.findByDisplayValue("express");
  fireEvent.click(screen.getByRole("button", { name: "Add train" }));
  expect(screen.getAllByDisplayValue("train_2")).toHaveLength(2);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Remove train_2" }));
  expect(screen.queryAllByDisplayValue("train_2")).toHaveLength(0);
  expect(screen.getByText("Saved")).toBeInTheDocument();
});

it("keeps an edited train ID input focused", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(configurationSnapshot()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
  renderPage();

  const input = await screen.findByLabelText("Train ID");
  input.focus();
  fireEvent.change(input, { target: { value: "express-2" } });

  expect(input).toHaveFocus();
});

it("keeps the original revision when a dirty draft outlives a refresh", async () => {
  const initial = configurationSnapshot();
  const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(
    new Response(JSON.stringify(initial), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  ));
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = renderPage();

  await screen.findByDisplayValue("express");
  fireEvent.change(screen.getByLabelText("BLE address"), {
    target: { value: "draft-address" },
  });
  queryClient.setQueryData(["configuration"], {
    ...initial,
    documents: {
      trains: {
        ...initial.documents.trains,
        modified_at: 1500,
        value: {
          trains: [{
            ...initial.documents.trains.value.trains[0],
            ble_address: "newer-address",
          }],
        },
      },
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save configuration" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  const body = JSON.parse(String(fetchMock.mock.calls[1][1]?.body));
  expect(body.documents.trains.base_modified_at).toBe(1000);
  expect(body.documents.trains.value.trains[0].ble_address).toBe("draft-address");
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
  return queryClient;
}

function configurationSnapshot(): ConfigurationSnapshot {
  return {
    version: 1,
    documents: {
      trains: {
        modified_at: 1000,
        restart_required: true,
        value: {
          trains: [
            {
              id: "express",
              lego_hub_id: "express-hub",
              ble_address: "AA:BB",
              tag_ids: ["04:AB"],
            },
          ],
        },
      },
    },
  };
}
