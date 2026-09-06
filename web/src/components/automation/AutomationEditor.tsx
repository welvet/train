"use client";

import {
  Alert,
  Badge,
  Box,
  Button,
  Group,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  VisuallyHidden,
} from "@mantine/core";

import { AutomationNodeList } from "./AutomationNodeEditor";
import {
  validateAutomationTopology,
  visitAutomationNodes,
} from "./automation-validation";
import type {
  AutomationDocument,
  AutomationNode,
  AutomationRule,
  AutomationTopology,
} from "./types";
import classes from "./automation.module.css";

interface AutomationEditorProps {
  readonly hubId: string;
  readonly detectorId: string;
  readonly topology: AutomationTopology;
  readonly document: AutomationDocument;
  readonly disabled?: boolean;
  readonly onDocumentChange: (document: AutomationDocument) => void;
}

export function AutomationEditor({
  hubId,
  detectorId,
  topology,
  document,
  disabled = false,
  onDocumentChange,
}: AutomationEditorProps) {
  const indexedRules = document.rules
    .map((rule, index) => ({ rule, index }))
    .filter(
      ({ rule }) =>
        rule.enabled &&
        rule.root.hub_id === hubId &&
        rule.root.detector_id === detectorId,
    );
  const availableTrainIds = topology.trainIds.filter(
    (trainId) => !indexedRules.some(({ rule }) => rule.root.train_id === trainId),
  );
  const localValidationError = getValidationError(
    { version: document.version, rules: indexedRules.map(({ rule }) => rule) },
    topology,
  );

  const setDocument = (next: AutomationDocument) => {
    onDocumentChange({
      ...next,
      version:
        next.version === 3
          ? 3
          : next.version === 2 || containsIfCount(next)
            ? 2
            : 1,
    });
  };

  const replaceRule = (index: number, next: AutomationRule) => {
    setDocument({
      version: document.version,
      rules: document.rules.map((rule, itemIndex) =>
        itemIndex === index ? { ...next, enabled: true } : rule,
      ),
    });
  };

  const createRule = () => {
    const trainId = availableTrainIds[0] ?? "";
    const next: AutomationRule = {
      id: uniqueRuleId(document, ruleId(hubId, detectorId, trainId)),
      enabled: true,
      root: {
        type: "train_detected",
        hub_id: hubId,
        detector_id: detectorId,
        train_id: trainId,
        children: [],
      },
    };
    setDocument({ version: document.version, rules: [...document.rules, next] });
  };

  const conflicts = sharedTargetWarnings(document).filter((warning) =>
    indexedRules.some(({ rule }) => warning.ruleIds.includes(rule.id)),
  );

  return (
    <fieldset disabled={disabled} className={classes.editorFieldset}>
      <VisuallyHidden component="legend">
        Automation for {hubId} / {detectorId}
      </VisuallyHidden>
      <Box mt="sm" className={classes.editor}>
        <Group justify="space-between" align="center">
          <Group gap="xs">
            <Text className={classes.titleEmoji} aria-hidden>⚙️</Text>
            <Text fw={800} size="sm">Automation</Text>
          </Group>
          {indexedRules.length > 0 && (
            <Badge color="green" variant="light" size="sm">⚡ On</Badge>
          )}
        </Group>

        {localValidationError && (
          <Alert color="red" title="Needs a fix" mt="sm">{localValidationError}</Alert>
        )}
        {conflicts.map((warning) => (
          <Alert color="yellow" title="Same track control" mt="sm" key={warning.key}>
            {warning.message}
          </Alert>
        ))}

        {indexedRules.length === 0 ? (
          <Paper withBorder radius="lg" p="sm" mt="xs" className={classes.emptyState}>
            <Stack align="center" gap="xs">
              <Button
                size="md"
                onClick={createRule}
                disabled={topology.trainIds.length === 0}
                aria-label={`Create automation for ${hubId} / ${detectorId}`}
              >
                🚂 Build
              </Button>
              {topology.trainIds.length === 0 && (
                <Text size="xs" c="orange">Add a tag to a train first</Text>
              )}
            </Stack>
          </Paper>
        ) : (
          <Stack gap="sm" mt="xs">
            {indexedRules.map(({ rule, index }) => (
              <RuleEditor
                key={`${index}-${rule.id}`}
                rule={rule}
                topology={topology}
                unavailableTrainIds={indexedRules
                  .filter((item) => item.index !== index)
                  .map((item) => item.rule.root.train_id)}
                onTrainChange={(trainId) =>
                  replaceRule(index, {
                    ...rule,
                    id: uniqueRuleId(
                      {
                        version: document.version,
                        rules: document.rules.filter((_, itemIndex) => itemIndex !== index),
                      },
                      ruleId(hubId, detectorId, trainId),
                    ),
                    root: { ...rule.root, train_id: trainId },
                  })
                }
                onChange={(next) => replaceRule(index, next)}
                onRemove={() =>
                  setDocument({
                    version: document.version,
                    rules: document.rules.filter((_, itemIndex) => itemIndex !== index),
                  })
                }
              />
            ))}
            <Button
              variant="light"
              size="md"
              className={classes.addRuleButton}
              onClick={createRule}
              disabled={availableTrainIds.length === 0}
              aria-label={`Add automation for another train at ${hubId} / ${detectorId}`}
            >
              ＋ 🚂
            </Button>
          </Stack>
        )}
      </Box>
    </fieldset>
  );
}

function RuleEditor({
  rule,
  topology,
  unavailableTrainIds,
  onTrainChange,
  onChange,
  onRemove,
}: {
  readonly rule: AutomationRule;
  readonly topology: AutomationTopology;
  readonly unavailableTrainIds: readonly string[];
  readonly onTrainChange: (trainId: string) => void;
  readonly onChange: (rule: AutomationRule) => void;
  readonly onRemove: () => void;
}) {
  return (
    <Paper withBorder radius="lg" p="sm" className={classes.ruleCard}>
      <Stack gap="sm">
        <fieldset className={classes.choiceFieldset}>
          <VisuallyHidden component="legend">Choose a train</VisuallyHidden>
          <SimpleGrid cols={{ base: 1, sm: Math.min(topology.trainIds.length, 3) }} spacing="xs">
            {topology.trainIds.map((trainId) => (
              <Button
                key={trainId}
                variant={rule.root.train_id === trainId ? "filled" : "light"}
                color="violet"
                size="md"
                className={classes.trainButton}
                disabled={unavailableTrainIds.includes(trainId)}
                onClick={() => onTrainChange(trainId)}
                aria-label={`Run when ${trainId} arrives`}
                aria-pressed={rule.root.train_id === trainId}
              >
                <span aria-hidden className={classes.buttonEmoji}>🚂</span>
                <span>{trainId}</span>
              </Button>
            ))}
          </SimpleGrid>
        </fieldset>

        <Text className={classes.flowArrow} aria-hidden>👇</Text>
        <AutomationNodeList
          nodes={rule.root.children}
          switches={topology.switches}
          accessibleLabel="Automation steps"
          onChange={(children) => onChange({ ...rule, root: { ...rule.root, children } })}
        />

        <Button
          variant="light"
          color="red"
          size="md"
          className={classes.removeRuleButton}
          onClick={onRemove}
          aria-label={`Remove automation for ${rule.root.train_id}`}
        >
          🗑️
        </Button>
      </Stack>
    </Paper>
  );
}

function ruleId(hubId: string, detectorId: string, trainId: string) {
  return `${hubId}_${detectorId}_${trainId || "train"}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "");
}

function uniqueRuleId(document: AutomationDocument, base: string) {
  const ids = new Set(document.rules.map((rule) => rule.id));
  if (!ids.has(base)) return base;
  let suffix = 2;
  while (ids.has(`${base}_${suffix}`)) suffix += 1;
  return `${base}_${suffix}`;
}

function sharedTargetWarnings(document: AutomationDocument) {
  const ruleTargets = new Map<string, { label: string; ruleIds: string[] }>();
  const warnings: Array<{
    key: string;
    message: string;
    ruleIds: string[];
  }> = [];
  for (const rule of document.rules.filter((item) => item.enabled)) {
    const analysis = analyzeConcurrentTargets(rule.root.children, rule.root.train_id);
    for (const [target, label] of analysis.conflicts) {
      warnings.push({
        key: `concurrent:${rule.id}:${target}`,
        message: `${label} is changed by concurrent paths in this rule.`,
        ruleIds: [rule.id],
      });
    }
    for (const [target, label] of analysis.targets) {
      const existing = ruleTargets.get(target);
      ruleTargets.set(target, {
        label,
        ruleIds: [...(existing?.ruleIds ?? []), rule.id],
      });
    }
  }
  for (const [target, { label, ruleIds }] of ruleTargets) {
    if (ruleIds.length > 1) {
      warnings.push({
        key: `rules:${target}`,
        message: `${label} is changed by more than one rule.`,
        ruleIds,
      });
    }
  }
  return warnings;
}

interface TargetAnalysis {
  targets: Map<string, string>;
  conflicts: Map<string, string>;
}

function analyzeConcurrentTargets(
  nodes: readonly AutomationNode[],
  trainId: string,
): TargetAnalysis {
  const targets = new Map<string, string>();
  const conflicts = new Map<string, string>();
  for (const node of nodes) {
    const child = analyzeTargetNode(node, trainId);
    for (const [target, label] of child.conflicts) conflicts.set(target, label);
    for (const [target, label] of child.targets) {
      if (targets.has(target)) conflicts.set(target, label);
      targets.set(target, label);
    }
  }
  return { targets, conflicts };
}

function analyzeTargetNode(
  node: AutomationNode,
  trainId: string,
): TargetAnalysis {
  if (node.type === "set_train_speed") {
    return targetAnalysis(`train\u0000${trainId}`, `Train ${trainId}`);
  }
  if (node.type === "set_switch") {
    return targetAnalysis(
      `switch\u0000${node.hub_id}\u0000${node.switch_id}`,
      `Switch ${node.hub_id} / ${node.switch_id}`,
    );
  }
  if (node.type === "if_count") {
    const alternatives = node.children.map((branch) =>
      analyzeConcurrentTargets(branch.children, trainId),
    );
    const targets = new Map<string, string>();
    const conflicts = new Map<string, string>();
    for (const alternative of alternatives) {
      for (const [target, label] of alternative.targets) targets.set(target, label);
      for (const [target, label] of alternative.conflicts) conflicts.set(target, label);
    }
    return { targets, conflicts };
  }
  return analyzeConcurrentTargets(node.children, trainId);
}

function targetAnalysis(target: string, label: string): TargetAnalysis {
  return {
    targets: new Map([[target, label]]),
    conflicts: new Map(),
  };
}

function containsIfCount(document: AutomationDocument): boolean {
  let found = false;
  for (const rule of document.rules) {
    visitAutomationNodes(rule.root.children, (node) => {
      if (node.type === "if_count") found = true;
    });
  }
  return found;
}

function getValidationError(
  document: AutomationDocument,
  topology: AutomationTopology,
): string | null {
  try {
    validateAutomationTopology(document, topology);
    return null;
  } catch (error) {
    return error instanceof Error ? error.message : "This automation needs a fix.";
  }
}
