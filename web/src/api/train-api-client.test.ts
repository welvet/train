import { ApiRequestError, TrainApiClient } from "./train-api-client";

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

function stateEnvelope() {
  return {
    version: 3 as const,
    snapshot_at: 2,
    automation: {
      document: { version: 1, rules: [] },
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
