import { ApiRequestError, TrainApiClient } from "./train-api-client";

describe("TrainApiClient", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reads a versioned state envelope", async () => {
    const envelope = stateEnvelope();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(envelope), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(new TrainApiClient().getState()).resolves.toEqual(envelope);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/state",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("marks a timed out command as having an unknown outcome", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: "command timed out" }), {
          status: 504,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    const result = new TrainApiClient().publishEvent({
      type: "set_train_speed",
      data: { train_id: "express", speed: 40 },
    });

    await expect(result).rejects.toMatchObject({
      message: "command timed out",
      outcomeUnknown: true,
      status: 504,
    } satisfies Partial<ApiRequestError>);
  });
});

function stateEnvelope() {
  return {
    version: 1 as const,
    state: {
      revision: 1,
      updated_at: 1,
      running: true,
      automation: { halted: false },
      trains: {},
      lego_hubs: {},
      arduino_hubs: {},
    },
  };
}
