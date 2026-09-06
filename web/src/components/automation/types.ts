export type SwitchPosition = "straight" | "diverge" | "flip";

export interface SetTrainSpeedNode {
  readonly type: "set_train_speed";
  readonly speed: number;
  readonly children: readonly [];
}

export interface SetSwitchNode {
  readonly type: "set_switch";
  readonly hub_id: string;
  readonly switch_id: string;
  readonly position: SwitchPosition;
  readonly children: readonly [];
}

export interface WaitNode {
  readonly type: "wait";
  readonly seconds: number;
  readonly children: readonly AutomationNode[];
}

export interface OnCountNode {
  readonly type: "on_count";
  readonly count: number;
  readonly children: readonly AutomationNode[];
}

export type BranchWhen = "match" | "otherwise";

export interface BranchNode {
  readonly type: "branch";
  readonly when: BranchWhen;
  readonly children: readonly AutomationNode[];
}

export interface IfCountNode {
  readonly type: "if_count";
  readonly count: number;
  readonly children: readonly [BranchNode, BranchNode];
}

export type AutomationNode =
  | SetTrainSpeedNode
  | SetSwitchNode
  | WaitNode
  | OnCountNode
  | IfCountNode
  | BranchNode;

export interface TrainDetectedNode {
  readonly type: "train_detected";
  readonly hub_id: string;
  readonly detector_id: string;
  readonly train_id: string;
  readonly children: readonly AutomationNode[];
}

export interface AutomationRule {
  readonly id: string;
  readonly enabled: boolean;
  readonly root: TrainDetectedNode;
}

export interface AutomationDocument {
  readonly version: 1 | 2;
  readonly rules: readonly AutomationRule[];
}

export interface SwitchOption {
  readonly hubId: string;
  readonly switchId: string;
}

export interface DetectorOption {
  readonly hubId: string;
  readonly detectorId: string;
}

export interface AutomationTopology {
  readonly trainIds: readonly string[];
  readonly switches: readonly SwitchOption[];
  readonly detectors: readonly DetectorOption[];
}
