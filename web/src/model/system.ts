export type ConnectionState = "loading" | "online" | "stale" | "offline";

export interface LegoHubModel {
  readonly id: string;
  readonly connected: boolean;
  readonly batteryPct: number;
  readonly voltage: number;
}

export interface TrainModel {
  readonly id: string;
  readonly speed: number;
  readonly legoHub: LegoHubModel | null;
}

export interface SwitchModel {
  readonly id: string;
  readonly angle: number;
}

export interface DetectorModel {
  readonly id: string;
  readonly available: boolean;
  readonly triggered: boolean;
  readonly trainId: string | null;
}

export interface ArduinoHubModel {
  readonly id: string;
  readonly deviceId: string | null;
  readonly connected: boolean;
  readonly switches: readonly SwitchModel[];
  readonly detectors: readonly DetectorModel[];
}

export interface SystemModel {
  readonly revision: number;
  readonly updatedAt: number;
  readonly running: boolean;
  readonly automationHalted: boolean;
  readonly trains: readonly TrainModel[];
  readonly arduinoHubs: readonly ArduinoHubModel[];
}
