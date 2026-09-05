"use client";

import {
  Alert,
  Badge,
  Box,
  Button,
  Group,
  NativeSelect,
  Paper,
  Stack,
  Switch,
  Text,
  Textarea,
  TextInput,
} from "@mantine/core";
import { useState } from "react";

import { AutomationNodeList } from "./AutomationNodeEditor";
import { parseAutomation, serializeAutomation } from "./automation-json";
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
  readonly onDocumentChange: (document: AutomationDocument) => void;
}

export function AutomationEditor({
  hubId,
  detectorId,
  topology,
  document,
  onDocumentChange,
}: AutomationEditorProps) {
  const [jsonOpen, setJsonOpen] = useState(false);
  const [jsonDraft, setJsonDraft] = useState("");
  const [jsonBase, setJsonBase] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [jsonApplied, setJsonApplied] = useState(false);
  const indexedRules = document.rules
    .map((rule, index) => ({ rule, index }))
    .filter(
      ({ rule }) =>
        rule.root.hub_id === hubId && rule.root.detector_id === detectorId,
    );
  const serialization = trySerialize(document, topology);
  const documentJson = serialization.json ?? "";
  const jsonStale = jsonOpen && (serialization.error !== null || jsonBase !== documentJson);

  const setDocument = (next: AutomationDocument) => {
    onDocumentChange(next);
    setJsonApplied(false);
  };

  const replaceRule = (index: number, next: AutomationRule) => {
    let rules = document.rules.map((rule, itemIndex) => (itemIndex === index ? next : rule));
    if (next.enabled) {
      rules = rules.map((rule, itemIndex) =>
        itemIndex !== index && sameTrigger(rule, next) ? { ...rule, enabled: false } : rule,
      );
    }
    setDocument({ version: 1, rules });
  };

  const createRule = () => {
    const trainId =
      topology.trainIds.find(
        (id) => !indexedRules.some(({ rule }) => rule.root.train_id === id),
      ) ?? topology.trainIds[0] ?? "";
    const id = uniqueRuleId(document, ruleId(hubId, detectorId, trainId));
    const next: AutomationRule = {
      id,
      enabled: !document.rules.some(
        (rule) =>
          rule.enabled &&
          rule.root.hub_id === hubId &&
          rule.root.detector_id === detectorId &&
          rule.root.train_id === trainId,
      ),
      root: {
        type: "train_detected",
        hub_id: hubId,
        detector_id: detectorId,
        train_id: trainId,
        children: [{ type: "set_train_speed", speed: 0, children: [] }],
      },
    };
    setDocument({ version: 1, rules: [...document.rules, next] });
  };

  const refreshJson = () => {
    if (serialization.error) {
      setJsonError(serialization.error);
      setJsonApplied(false);
      return;
    }
    setJsonDraft(documentJson);
    setJsonBase(documentJson);
    setJsonError(null);
    setJsonApplied(false);
  };

  const toggleJson = () => {
    if (!jsonOpen) {
      if (serialization.error) {
        setJsonError(serialization.error);
        return;
      }
      refreshJson();
    }
    setJsonOpen((open) => !open);
  };

  const applyJson = () => {
    if (jsonStale) {
      setJsonError("The visual draft changed after this JSON snapshot. Regenerate before applying.");
      return;
    }
    try {
      const next = parseAutomation(jsonDraft);
      validateTopology(next, topology);
      onDocumentChange(next);
      const serialized = serializeAutomation(next);
      setJsonDraft(serialized);
      setJsonBase(serialized);
      setJsonError(null);
      setJsonApplied(true);
    } catch (error) {
      setJsonApplied(false);
      setJsonError(error instanceof Error ? error.message : "Could not apply JSON.");
    }
  };

  const conflicts = sharedTargetWarnings(document).filter((warning) =>
    indexedRules.some(({ rule }) => warning.ruleIds.includes(rule.id)),
  );

  return (
    <Box mt="md" className={classes.editor}>
      <Group justify="space-between" align="center" wrap="wrap" gap="xs">
        <Group gap="xs">
          <Text fw={700} size="sm">Automation</Text>
          <Badge color="gray" variant="light">Local draft</Badge>
        </Group>
        <Button
          variant="subtle"
          size="compact-sm"
          onClick={toggleJson}
          disabled={!jsonOpen && serialization.error !== null}
          aria-label={`${jsonOpen ? "Hide" : "View"} automation JSON for ${hubId} / ${detectorId}`}
        >
          {jsonOpen ? "Hide JSON" : "View JSON"}
        </Button>
      </Group>
      <Text size="xs" c="dimmed" mt={2}>
        Runs when a configured train is detected here. Backend saving comes later.
      </Text>
      {!jsonOpen && serialization.error && (
        <Text size="xs" c="red" mt={2}>{serialization.error}</Text>
      )}

      {jsonOpen && (
        <Paper withBorder radius="md" p="sm" mt="sm">
          <Stack gap="xs">
            <Textarea
              label="Complete automation JSON"
              aria-label={`Complete automation JSON for ${hubId} / ${detectorId}`}
              description="Import or export the version 1 document for every detector"
              rows={12}
              ff="monospace"
              value={jsonDraft}
              onChange={(event) => {
                setJsonDraft(event.currentTarget.value);
                setJsonApplied(false);
              }}
            />
            {jsonStale && (
              <Alert color="yellow" title="JSON snapshot is out of date">
                The visual draft changed. Regenerate the JSON before applying edits from it.
              </Alert>
            )}
            {jsonError && <Alert color="red" title="JSON not applied">{jsonError}</Alert>}
            {jsonApplied && (
              <Alert color="green" title="JSON applied to the visual draft">
                Every detector now reflects the parsed document.
              </Alert>
            )}
            <Group justify="flex-end">
              <Button
                variant="default"
                size="xs"
                onClick={refreshJson}
                disabled={serialization.error !== null}
              >
                Regenerate
              </Button>
              <Button size="xs" onClick={applyJson} disabled={jsonStale}>Apply JSON</Button>
            </Group>
          </Stack>
        </Paper>
      )}

      {conflicts.map((warning) => (
        <Alert color="yellow" title="Shared automation target" mt="sm" key={warning.target}>
          {warning.target} is used by enabled rules {warning.ruleIds.join(" and ")}.
        </Alert>
      ))}

      {indexedRules.length === 0 ? (
        <Paper withBorder radius="md" p="md" mt="sm" className={classes.emptyState}>
          <Stack gap="xs" align="flex-start">
            <Text size="sm" fw={700}>No automation for this detector</Text>
            <Text size="xs" c="dimmed">Add a local draft and arrange its steps in execution order.</Text>
            <Button
              size="xs"
              onClick={createRule}
              disabled={topology.trainIds.length === 0}
              aria-label={`Create automation for ${hubId} / ${detectorId}`}
            >
              Create automation
            </Button>
            {topology.trainIds.length === 0 && (
              <Text size="xs" c="orange">Configure a train before creating this trigger.</Text>
            )}
          </Stack>
        </Paper>
      ) : (
        <Stack gap="sm" mt="sm">
          {indexedRules.map(({ rule, index }) => (
            <RuleEditor
              key={`${index}-${rule.id}`}
              rule={rule}
              topology={topology}
              duplicateId={document.rules.some((item, itemIndex) => itemIndex !== index && item.id === rule.id)}
              onChange={(next) => replaceRule(index, next)}
              onRemove={() =>
                setDocument({
                  version: 1,
                  rules: document.rules.filter((_, itemIndex) => itemIndex !== index),
                })
              }
            />
          ))}
          <Button
            variant="light"
            size="xs"
            onClick={createRule}
            disabled={topology.trainIds.length === 0}
            aria-label={`Add alternative automation for ${hubId} / ${detectorId}`}
            style={{ alignSelf: "flex-start" }}
          >
            + Add alternative rule
          </Button>
        </Stack>
      )}
    </Box>
  );
}

function RuleEditor({
  rule,
  topology,
  duplicateId,
  onChange,
  onRemove,
}: {
  readonly rule: AutomationRule;
  readonly topology: AutomationTopology;
  readonly duplicateId: boolean;
  readonly onChange: (rule: AutomationRule) => void;
  readonly onRemove: () => void;
}) {
  return (
    <Paper withBorder radius="md" p="sm" className={classes.ruleCard}>
      <Stack gap="sm">
        <Group justify="space-between" align="flex-start" wrap="wrap">
          <TextInput
            label="Rule name"
            value={rule.id}
            error={!rule.id.trim() ? "Rule name is required" : duplicateId ? "Rule name must be unique" : undefined}
            onChange={(event) => onChange({ ...rule, id: event.currentTarget.value })}
            className={classes.ruleName}
          />
          <Switch
            label="Enabled"
            checked={rule.enabled}
            onChange={(event) => onChange({ ...rule, enabled: event.currentTarget.checked })}
            mt={26}
          />
        </Group>
        <NativeSelect
          label="When this train arrives"
          data={topology.trainIds}
          value={rule.root.train_id}
          onChange={(event) => {
            onChange({ ...rule, root: { ...rule.root, train_id: event.currentTarget.value } });
          }}
        />
        <div>
          <Text size="xs" c="dimmed" fw={700} mb="xs">Do these steps in order</Text>
          <AutomationNodeList
            nodes={rule.root.children}
            switches={topology.switches}
            onChange={(children) => onChange({ ...rule, root: { ...rule.root, children } })}
          />
        </div>
        <Group justify="space-between">
          <Text size="xs" c="dimmed">
            Starting with a train already here can run this rule immediately.
          </Text>
          <Button
            variant="subtle"
            color="red"
            size="xs"
            onClick={onRemove}
            aria-label={`Remove rule ${rule.id}`}
          >
            Remove rule
          </Button>
        </Group>
      </Stack>
    </Paper>
  );
}

function sameTrigger(left: AutomationRule, right: AutomationRule) {
  return (
    left.root.hub_id === right.root.hub_id &&
    left.root.detector_id === right.root.detector_id &&
    left.root.train_id === right.root.train_id
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

function validateTopology(document: AutomationDocument, topology: AutomationTopology) {
  const detectors = new Set(topology.detectors.map((item) => `${item.hubId}\u0000${item.detectorId}`));
  const switches = new Set(topology.switches.map((item) => `${item.hubId}\u0000${item.switchId}`));
  for (const rule of document.rules) {
    if (!detectors.has(`${rule.root.hub_id}\u0000${rule.root.detector_id}`)) {
      throw new Error(`Detector ${rule.root.hub_id} / ${rule.root.detector_id} is not configured.`);
    }
    if (!topology.trainIds.includes(rule.root.train_id)) {
      throw new Error(`Train ${rule.root.train_id} is not configured.`);
    }
    visitNodes(rule.root.children, (node) => {
      if (node.type === "set_switch" && !switches.has(`${node.hub_id}\u0000${node.switch_id}`)) {
        throw new Error(`Switch ${node.hub_id} / ${node.switch_id} is not configured.`);
      }
    });
  }
}

function sharedTargetWarnings(document: AutomationDocument) {
  const targets = new Map<string, string[]>();
  for (const rule of document.rules.filter((item) => item.enabled)) {
    const ruleTargets = new Set<string>();
    visitNodes(rule.root.children, (node) => {
      if (node.type === "set_train_speed") ruleTargets.add(`Train ${rule.root.train_id}`);
      if (node.type === "set_switch") ruleTargets.add(`Switch ${node.hub_id} / ${node.switch_id}`);
    });
    for (const target of ruleTargets) targets.set(target, [...(targets.get(target) ?? []), rule.id]);
  }
  return [...targets.entries()]
    .filter(([, ruleIds]) => ruleIds.length > 1)
    .map(([target, ruleIds]) => ({ target, ruleIds }));
}

function visitNodes(nodes: readonly AutomationNode[], visit: (node: AutomationNode) => void) {
  for (const node of nodes) {
    visit(node);
    if (node.type === "wait" || node.type === "on_count") visitNodes(node.children, visit);
  }
}

function trySerialize(
  document: AutomationDocument,
  topology: AutomationTopology,
): { json: string | null; error: string | null } {
  try {
    validateTopology(document, topology);
    return { json: serializeAutomation(document), error: null };
  } catch (error) {
    return {
      json: null,
      error: error instanceof Error ? error.message : "The automation draft is invalid.",
    };
  }
}
