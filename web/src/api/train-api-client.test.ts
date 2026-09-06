import {
  ApiRequestError,
  type ConfigurationSnapshot,
  type StateEnvelope,
  TrainApiClient,
} from "./train-api-client";

describe("TrainApiClient", () => {
  afterEach(() => {
    vi.useRealTimers();
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

  it("reads and replaces the versioned configuration envelope", async () => {
    const configuration = configurationSnapshot();
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify(configuration), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ));
    vi.stubGlobal("fetch", fetchMock);
    const client = new TrainApiClient();

    await expect(client.getConfiguration()).resolves.toEqual(configuration);
    const update = {
      version: 1 as const,
      documents: {
        trains: {
          base_modified_at: 1000,
          modified_at: 2000,
          value: configuration.documents.trains.value,
        },
      },
    };
    await expect(client.replaceConfiguration(update)).resolves.toEqual(
      configuration,
    );

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/configuration",
      expect.objectContaining({ cache: "no-store" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/configuration",
      expect.objectContaining({ method: "PUT", body: JSON.stringify(update) }),
    );
  });

  it("accepts a trains-only v1 snapshot during backend rollback", async () => {
    const configuration = configurationSnapshot();
    delete configuration.documents.arduinos;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify(configuration), { status: 200 }),
    ));

    await expect(new TrainApiClient().getConfiguration()).resolves.toEqual(
      configuration,
    );
  });

  it("rejects malformed Arduino configuration responses", async () => {
    const configuration = configurationSnapshot();
    configuration.documents.arduinos!.value.devices.arduino_1.backend_port = 0;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify(configuration), { status: 200 }),
    ));

    await expect(new TrainApiClient().getConfiguration()).rejects.toMatchObject({
      message: "The backend returned an unsupported configuration format",
    });
  });

  it("sends Arduino updates as one document", async () => {
    const configuration = configurationSnapshot();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(configuration), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const update = {
      version: 1 as const,
      documents: {
        arduinos: {
          base_modified_at: 1000,
          value: configuration.documents.arduinos!.value,
        },
      },
    };

    await new TrainApiClient().replaceConfiguration(update);

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual(update);
  });

  it("keeps configuration updates document-exclusive at compile time", () => {
    const client = new TrainApiClient();
    const configuration = configurationSnapshot();
    if (false) {
      void client.replaceConfiguration({
        version: 1,
        // @ts-expect-error a replacement must contain exactly one document
        documents: {
          trains: { base_modified_at: 1, value: configuration.documents.trains.value },
          arduinos: { base_modified_at: 1, value: configuration.documents.arduinos!.value },
        },
      });
    }
    expect(client).toBeInstanceOf(TrainApiClient);
  });

  it("rejects malformed configuration responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ version: 1, documents: {} }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(new TrainApiClient().getConfiguration()).rejects.toMatchObject({
      message: "The backend returned an unsupported configuration format",
      status: 0,
    });
  });

  it("rejects an empty train configuration response", async () => {
    const configuration = configurationSnapshot();
    configuration.documents.trains.value.trains = [];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(configuration), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(new TrainApiClient().getConfiguration()).rejects.toMatchObject({
      message: "The backend returned an unsupported configuration format",
      status: 0,
    });
  });

  it("rejects malformed automation in a state envelope", async () => {
    const envelope = stateEnvelope();
    envelope.automation.document = {};
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(envelope), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(new TrainApiClient().getState()).rejects.toMatchObject({
      message: "The backend returned an unsupported automation format",
      status: 0,
    });
  });

  it("rejects state without automation-eligible train ids", async () => {
    const envelope = stateEnvelope();
    Reflect.deleteProperty(envelope.automation, "eligible_train_ids");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(envelope), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(new TrainApiClient().getState()).rejects.toMatchObject({
      message: "The backend returned an unsupported state format",
      status: 0,
    });
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

  it("includes backend validation paths in request errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: "train has no configured tag: express",
            path: "$.rules[0].root.train_id",
          }),
          {
            status: 400,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    await expect(
      new TrainApiClient().replaceAutomation({ version: 1, rules: [] }),
    ).rejects.toMatchObject({
      message: "$.rules[0].root.train_id: train has no configured tag: express",
      status: 400,
    });
  });

  it("replaces the complete automation document", async () => {
    const document = {
      version: 1 as const,
      rules: [],
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          automation: { document, eligible_train_ids: [], paused: false, statuses: [] },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(new TrainApiClient().replaceAutomation(document)).resolves.toEqual(
      document,
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/automation",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify(document),
      }),
    );
  });

  it("rejects an unsupported automation update response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ automation: { document: {} } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(
      new TrainApiClient().replaceAutomation({ version: 1, rules: [] }),
    ).rejects.toMatchObject({
      message: "The backend returned an unsupported automation format",
      status: 0,
    });
  });

  it("applies complete state snapshots from the live stream", () => {
    const source = new FakeEventSource();
    vi.stubGlobal("EventSource", vi.fn(() => source));
    const onState = vi.fn();

    const unsubscribe = new TrainApiClient().subscribeToState(onState, vi.fn());
    source.emit("state", JSON.stringify(stateEnvelope()));

    expect(onState).toHaveBeenCalledWith(stateEnvelope());
    unsubscribe();
    expect(source.close).toHaveBeenCalledOnce();
  });

  it("reports malformed stream messages without closing the stream", () => {
    const source = new FakeEventSource();
    vi.stubGlobal("EventSource", vi.fn(() => source));
    const onState = vi.fn();
    const onError = vi.fn();

    const unsubscribe = new TrainApiClient().subscribeToState(onState, onError);
    source.emit("state", "not JSON");

    expect(onState).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledOnce();
    expect(source.close).not.toHaveBeenCalled();
    unsubscribe();
  });

  it("restarts the live stream after a connection failure", () => {
    vi.useFakeTimers();
    const sources: FakeEventSource[] = [];
    const EventSourceMock = vi.fn(() => {
      const source = new FakeEventSource();
      sources.push(source);
      return source;
    });
    vi.stubGlobal("EventSource", EventSourceMock);
    const onError = vi.fn();

    const unsubscribe = new TrainApiClient().subscribeToState(vi.fn(), onError);
    sources[0].fail();

    expect(sources[0].close).toHaveBeenCalledOnce();
    expect(onError).toHaveBeenCalledOnce();
    vi.advanceTimersByTime(2_000);
    expect(EventSourceMock).toHaveBeenCalledTimes(2);

    sources[0].fail();
    expect(onError).toHaveBeenCalledOnce();
    expect(sources[1].close).not.toHaveBeenCalled();

    sources[1].fail();
    vi.advanceTimersByTime(3_999);
    expect(EventSourceMock).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(1);
    expect(EventSourceMock).toHaveBeenCalledTimes(3);

    unsubscribe();
    expect(sources[2].close).toHaveBeenCalledOnce();
    sources[2].fail();
    vi.advanceTimersByTime(2_000);
    expect(onError).toHaveBeenCalledTimes(2);
    expect(EventSourceMock).toHaveBeenCalledTimes(3);
  });

  it("retries when opening the live stream throws", () => {
    vi.useFakeTimers();
    const source = new FakeEventSource();
    const EventSourceMock = vi
      .fn()
      .mockImplementationOnce(() => {
        throw new Error("blocked");
      })
      .mockImplementationOnce(() => source);
    vi.stubGlobal("EventSource", EventSourceMock);
    const onError = vi.fn();

    const unsubscribe = new TrainApiClient().subscribeToState(vi.fn(), onError);

    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: "blocked" }),
    );
    vi.advanceTimersByTime(2_000);
    expect(EventSourceMock).toHaveBeenCalledTimes(2);

    unsubscribe();
    expect(source.close).toHaveBeenCalledOnce();
  });
});

class FakeEventSource {
  onerror: (() => void) | null = null;
  close = vi.fn();
  private listeners = new Map<string, (event: MessageEvent<string>) => void>();

  addEventListener(
    type: string,
    listener: (event: MessageEvent<string>) => void,
  ): void {
    this.listeners.set(type, listener);
  }

  emit(type: string, data: string): void {
    this.listeners.get(type)?.(new MessageEvent(type, { data }));
  }

  fail(): void {
    this.onerror?.();
  }
}

function stateEnvelope(): StateEnvelope {
  return {
    version: 4 as const,
    snapshot_at: 2,
    automation: {
      document: { version: 1, rules: [] },
      eligible_train_ids: [],
      paused: false,
      statuses: [],
    },
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
              allow_legacy_hello: true,
              switches: [],
              readers: [],
            },
          },
        },
      },
    },
  };
}
