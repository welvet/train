import type {
  AutomationDocument,
  AutomationNode,
  AutomationTopology,
} from "./types";

export function validateAutomationTopology(
  document: AutomationDocument,
  topology: AutomationTopology,
): void {
  const detectors = new Set(
    topology.detectors.map(
      (item) => `${item.hubId}\u0000${item.detectorId}`,
    ),
  );
  const switches = new Set(
    topology.switches.map((item) => `${item.hubId}\u0000${item.switchId}`),
  );

  for (const rule of document.rules) {
    if (!detectors.has(`${rule.root.hub_id}\u0000${rule.root.detector_id}`)) {
      throw new Error(
        `Detector ${rule.root.hub_id} / ${rule.root.detector_id} is not configured.`,
      );
    }
    if (!topology.trainIds.includes(rule.root.train_id)) {
      throw new Error(`Train ${rule.root.train_id} is not configured.`);
    }
    visitAutomationNodes(rule.root.children, (node) => {
      if (
        node.type === "set_switch" &&
        !switches.has(`${node.hub_id}\u0000${node.switch_id}`)
      ) {
        throw new Error(
          `Switch ${node.hub_id} / ${node.switch_id} is not configured.`,
        );
      }
    });
  }
}

export function visitAutomationNodes(
  nodes: readonly AutomationNode[],
  visit: (node: AutomationNode) => void,
): void {
  for (const node of nodes) {
    visit(node);
    if (
      node.type === "wait" ||
      node.type === "on_count" ||
      node.type === "if_count" ||
      node.type === "branch"
    ) {
      visitAutomationNodes(node.children, visit);
    }
  }
}
