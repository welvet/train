import type {
  AutomationDocument,
  AutomationNode,
  AutomationRule,
  SwitchPosition,
} from "./types";

const MAX_RULES = 1_000;
const MAX_NODES_PER_RULE = 1_000;
const MAX_TREE_DEPTH = 64;

export function serializeAutomation(document: AutomationDocument): string {
  return JSON.stringify(validateAutomation(document), null, 2);
}

export function validateAutomation(document: unknown): AutomationDocument {
  return parseAutomation(JSON.stringify(document));
}

export function parseAutomation(source: string): AutomationDocument {
  let input: unknown;
  try {
    input = JSON.parse(source);
  } catch {
    throw new Error("Enter valid JSON before applying the draft.");
  }

  const value = object(input, "Automation document");
  exactKeys(value, ["version", "rules"], "Automation document");
  if (value.version !== 1 && value.version !== 2) {
    throw new Error("Only automation document versions 1 and 2 are supported.");
  }
  if (!Array.isArray(value.rules)) {
    throw new Error("Automation document rules must be an array.");
  }
  if (value.rules.length > MAX_RULES) {
    throw new Error(`Automation document may contain at most ${MAX_RULES} rules.`);
  }

  const rules = value.rules.map((rule, index) => parseRule(rule, index, value.version as 1 | 2));
  const ids = new Set<string>();
  const enabledTriggers = new Set<string>();
  for (const rule of rules) {
    if (ids.has(rule.id)) throw new Error(`Rule id ${rule.id} is used more than once.`);
    ids.add(rule.id);
    if (rule.enabled) {
      const trigger = `${rule.root.hub_id}\u0000${rule.root.detector_id}\u0000${rule.root.train_id}`;
      if (enabledTriggers.has(trigger)) {
        throw new Error("Only one rule for a detector and train pair may be enabled.");
      }
      enabledTriggers.add(trigger);
    }
  }

  return { version: value.version as 1 | 2, rules };
}

function parseRule(input: unknown, index: number, version: 1 | 2): AutomationRule {
  const label = `Rule ${index + 1}`;
  const value = object(input, label);
  exactKeys(value, ["id", "enabled", "root"], label);
  const id = nonEmptyString(value.id, `${label} id`);
  if (typeof value.enabled !== "boolean") {
    throw new Error(`${label} enabled must be true or false.`);
  }

  const root = object(value.root, `${label} root`);
  exactKeys(
    root,
    ["type", "hub_id", "detector_id", "train_id", "children"],
    `${label} root`,
  );
  if (root.type !== "train_detected") {
    throw new Error(`${label} root must have type train_detected.`);
  }
  const nodeCount = { value: 0 };
  const children = childrenOf(
    root.children,
    `${label} root`,
    nodeCount,
    1,
    version,
    "train_detected",
  );
  if (children.length === 0) throw new Error(`${label} root needs at least one step.`);
  return {
    id,
    enabled: value.enabled,
    root: {
      type: "train_detected",
      hub_id: nonEmptyString(root.hub_id, `${label} root hub_id`),
      detector_id: nonEmptyString(root.detector_id, `${label} root detector_id`),
      train_id: nonEmptyString(root.train_id, `${label} root train_id`),
      children,
    },
  };
}

function parseNode(
  input: unknown,
  path: string,
  nodeCount: { value: number },
  depth: number,
  version: 1 | 2,
  parentType: string,
): AutomationNode {
  if (depth > MAX_TREE_DEPTH) {
    throw new Error(`${path} tree depth must not exceed ${MAX_TREE_DEPTH}.`);
  }
  nodeCount.value += 1;
  if (nodeCount.value > MAX_NODES_PER_RULE) {
    throw new Error(`Rule may contain at most ${MAX_NODES_PER_RULE} nodes.`);
  }
  const value = object(input, path);
  if ((value.type === "if_count" || value.type === "branch") && version < 2) {
    throw new Error(`${path} type ${String(value.type)} requires automation document version 2.`);
  }
  if (value.type === "branch" && parentType !== "if_count") {
    throw new Error(`${path} branch is only allowed directly under if_count.`);
  }
  switch (value.type) {
    case "set_train_speed": {
      exactKeys(value, ["type", "speed", "children"], path);
      emptyChildren(value.children, path);
      const speed = value.speed;
      if (
        typeof speed !== "number" ||
        !Number.isInteger(speed) ||
        speed < -100 ||
        speed > 100
      ) {
        throw new Error(`${path} speed must be an integer from -100 to 100.`);
      }
      return { type: "set_train_speed", speed, children: [] };
    }
    case "set_switch": {
      exactKeys(value, ["type", "hub_id", "switch_id", "position", "children"], path);
      emptyChildren(value.children, path);
      if (
        value.position !== "straight" &&
        value.position !== "diverge" &&
        value.position !== "flip"
      ) {
        throw new Error(`${path} position must be straight, diverge, or flip.`);
      }
      return {
        type: "set_switch",
        hub_id: nonEmptyString(value.hub_id, `${path} hub_id`),
        switch_id: nonEmptyString(value.switch_id, `${path} switch_id`),
        position: value.position as SwitchPosition,
        children: [],
      };
    }
    case "wait": {
      exactKeys(value, ["type", "seconds", "children"], path);
      if (
        typeof value.seconds !== "number" ||
        !Number.isFinite(value.seconds) ||
        value.seconds < 0 ||
        value.seconds > 3600
      ) {
        throw new Error(`${path} seconds must be a finite number from 0 to 3600.`);
      }
      const children = childrenOf(value.children, path, nodeCount, depth + 1, version, "wait");
      if (children.length === 0) throw new Error(`${path} needs at least one child step.`);
      return { type: "wait", seconds: value.seconds, children };
    }
    case "on_count": {
      exactKeys(value, ["type", "count", "children"], path);
      if (!Number.isInteger(value.count) || Number(value.count) < 1) {
        throw new Error(`${path} count must be a positive whole number.`);
      }
      const children = childrenOf(value.children, path, nodeCount, depth + 1, version, "on_count");
      if (children.length === 0) throw new Error(`${path} needs at least one child step.`);
      return {
        type: "on_count",
        count: Number(value.count),
        children,
      };
    }
    case "if_count": {
      exactKeys(value, ["type", "count", "children"], path);
      if (!Number.isInteger(value.count) || Number(value.count) < 1) {
        throw new Error(`${path} count must be a positive whole number.`);
      }
      if (!Array.isArray(value.children) || value.children.length !== 2) {
        throw new Error(`${path} must contain one match branch and one otherwise branch.`);
      }
      const children = childrenOf(
        value.children,
        path,
        nodeCount,
        depth + 1,
        version,
        "if_count",
      );
      if (!children.every((child) => child.type === "branch")) {
        throw new Error(`${path} children must be branch steps.`);
      }
      const branches = children as [Extract<AutomationNode, { type: "branch" }>, Extract<AutomationNode, { type: "branch" }>];
      if (new Set(branches.map((branch) => branch.when)).size !== 2) {
        throw new Error(`${path} needs one match branch and one otherwise branch.`);
      }
      return { type: "if_count", count: Number(value.count), children: branches };
    }
    case "branch": {
      exactKeys(value, ["type", "when", "children"], path);
      if (value.when !== "match" && value.when !== "otherwise") {
        throw new Error(`${path} when must be match or otherwise.`);
      }
      const children = childrenOf(value.children, path, nodeCount, depth + 1, version, "branch");
      if (children.length === 0) throw new Error(`${path} needs at least one child step.`);
      return { type: "branch", when: value.when, children };
    }
    default:
      throw new Error(`${path} has an unsupported node type.`);
  }
}

function childrenOf(
  input: unknown,
  path: string,
  nodeCount: { value: number },
  depth: number,
  version: 1 | 2,
  parentType: string,
): AutomationNode[] {
  if (!Array.isArray(input)) throw new Error(`${path} children must be an array.`);
  return input.map((child, index) =>
    parseNode(child, `${path} child ${index + 1}`, nodeCount, depth, version, parentType),
  );
}

function emptyChildren(input: unknown, path: string) {
  if (!Array.isArray(input) || input.length !== 0) {
    throw new Error(`${path} is a terminal step and cannot have children.`);
  }
}

function object(input: unknown, label: string): Record<string, unknown> {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new Error(`${label} must be an object.`);
  }
  return input as Record<string, unknown>;
}

function nonEmptyString(input: unknown, label: string): string {
  if (typeof input !== "string" || input.trim() === "") {
    throw new Error(`${label} must be a non-empty string.`);
  }
  return input.trim();
}

function exactKeys(value: Record<string, unknown>, expected: string[], label: string) {
  const expectedSet = new Set(expected);
  const extra = Object.keys(value).find((key) => !expectedSet.has(key));
  const missing = expected.find((key) => !(key in value));
  if (extra) throw new Error(`${label} contains unknown field ${extra}.`);
  if (missing) throw new Error(`${label} is missing field ${missing}.`);
}
