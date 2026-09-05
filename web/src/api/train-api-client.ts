import type { components } from "./generated/schema";

export type StateEnvelope = components["schemas"]["StateEnvelope"];
export type PublicEvent = components["schemas"]["PublicEvent"];
export type CommandResponse = components["schemas"]["CommandResponse"];

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }

  get outcomeUnknown(): boolean {
    return this.status === 504;
  }
}

export class TrainApiClient {
  constructor(private readonly baseUrl = "") {}

  async getState(signal?: AbortSignal): Promise<StateEnvelope> {
    const response = await fetch(this.url("/api/state"), {
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal,
    });
    if (!response.ok) {
      throw await this.errorFrom(response);
    }

    const body: unknown = await response.json();
    if (!isStateEnvelope(body)) {
      throw new ApiRequestError("The backend returned an unsupported state format", 0);
    }
    return body;
  }

  async publishEvent(event: PublicEvent): Promise<CommandResponse> {
    const response = await fetch(this.url("/api/events"), {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(event),
    });
    if (!response.ok) {
      throw await this.errorFrom(response);
    }
    return (await response.json()) as CommandResponse;
  }

  private url(path: string): string {
    return `${this.baseUrl.replace(/\/$/, "")}${path}`;
  }

  private async errorFrom(response: Response): Promise<ApiRequestError> {
    let message = `Backend request failed (${response.status})`;
    try {
      const body = (await response.json()) as { error?: unknown };
      if (typeof body.error === "string") {
        message = body.error;
      }
    } catch {
      // Keep the status-based fallback when the body is not JSON.
    }
    return new ApiRequestError(message, response.status);
  }
}

function isStateEnvelope(value: unknown): value is StateEnvelope {
  if (!isRecord(value) || value.version !== 1 || !isRecord(value.state)) {
    return false;
  }
  const state = value.state;
  return (
    typeof state.revision === "number" &&
    typeof state.updated_at === "number" &&
    typeof state.running === "boolean" &&
    isRecord(state.automation) &&
    isRecord(state.trains) &&
    isRecord(state.lego_hubs) &&
    isRecord(state.arduino_hubs)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
