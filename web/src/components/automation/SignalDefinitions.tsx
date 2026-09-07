import { ActionIcon, Button, Group, Paper, Stack, Text, TextInput, Tooltip } from "@mantine/core";
import { useState } from "react";

import type { AutomationDocument, AutomationNode } from "./types";

export function SignalDefinitions({
  document,
  disabled = false,
  onChange,
}: {
  readonly document: AutomationDocument;
  readonly disabled?: boolean;
  readonly onChange: (document: AutomationDocument) => void;
}) {
  const referenced = referencedSignals(document);
  const addSignal = () => {
    let suffix = 1;
    while (document.signals.includes(`signal_${suffix}`)) suffix += 1;
    onChange({ ...document, signals: [...document.signals, `signal_${suffix}`] });
  };

  return (
    <Paper component="section" aria-label="Automation signals" withBorder radius="md" p="sm">
      <Stack gap="xs">
        <Group justify="space-between" align="center">
          <div>
            <Text fw={800} size="sm">Signals</Text>
            <Text size="xs" c="dimmed">Integer values start at 0 when automation is loaded</Text>
          </div>
          <Button
            variant="light"
            size="xs"
            disabled={disabled}
            onClick={addSignal}
            aria-label="Add signal"
          >
            ＋ Signal
          </Button>
        </Group>
        {document.signals.length === 0 ? (
          <Text size="xs" c="dimmed">No signals yet.</Text>
        ) : (
          document.signals.map((signal) => (
            <SignalRow
              key={signal}
              signal={signal}
              signals={document.signals}
              referenced={referenced.has(signal)}
              disabled={disabled}
              onRename={(next) => onChange(renameSignal(document, signal, next))}
              onRemove={() =>
                onChange({
                  ...document,
                  signals: document.signals.filter((item) => item !== signal),
                })
              }
            />
          ))
        )}
      </Stack>
    </Paper>
  );
}

function SignalRow({
  signal,
  signals,
  referenced,
  disabled,
  onRename,
  onRemove,
}: {
  readonly signal: string;
  readonly signals: readonly string[];
  readonly referenced: boolean;
  readonly disabled: boolean;
  readonly onRename: (signal: string) => void;
  readonly onRemove: () => void;
}) {
  const [draft, setDraft] = useState({ source: signal, value: signal });
  const value = draft.source === signal ? draft.value : signal;
  const normalized = value.trim();
  const error =
    normalized.length === 0
      ? "Enter a signal name"
      : normalized !== signal && signals.includes(normalized)
        ? "Signal names must be unique"
        : undefined;

  const commit = () => {
    if (error) {
      setDraft({ source: signal, value: signal });
      return;
    }
    if (normalized !== signal) onRename(normalized);
  };

  return (
    <Group align="flex-start" wrap="nowrap">
      <TextInput
        aria-label={`Signal name ${signal}`}
        value={value}
        error={error}
        disabled={disabled}
        onChange={(event) => setDraft({ source: signal, value: event.currentTarget.value })}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.currentTarget.blur();
        }}
        styles={{ root: { flex: 1 } }}
      />
      <Tooltip label={referenced ? "Remove its automation steps first" : "Remove signal"}>
        <span>
          <ActionIcon
            variant="light"
            color="red"
            size="lg"
            disabled={disabled || referenced}
            onClick={onRemove}
            aria-label={`Remove signal ${signal}`}
          >
            🗑️
          </ActionIcon>
        </span>
      </Tooltip>
    </Group>
  );
}

function referencedSignals(document: AutomationDocument): Set<string> {
  const result = new Set<string>();
  for (const rule of document.rules) collectReferences(rule.root.children, result);
  return result;
}

function collectReferences(nodes: readonly AutomationNode[], result: Set<string>): void {
  for (const node of nodes) {
    if (
      node.type === "set_signal" ||
      node.type === "on_signal" ||
      node.type === "if_signal" ||
      node.type === "when_signal_is"
    ) {
      result.add(node.signal);
    }
    if ("children" in node) collectReferences(node.children, result);
  }
}

function renameSignal(
  document: AutomationDocument,
  previous: string,
  next: string,
): AutomationDocument {
  return {
    ...document,
    signals: document.signals.map((signal) => (signal === previous ? next : signal)),
    rules: document.rules.map((rule) => ({
      ...rule,
      root: { ...rule.root, children: renameReferences(rule.root.children, previous, next) },
    })),
  };
}

function renameReferences(
  nodes: readonly AutomationNode[],
  previous: string,
  next: string,
): readonly AutomationNode[] {
  return nodes.map((node) => {
    const renamed =
      (node.type === "set_signal" ||
        node.type === "on_signal" ||
        node.type === "if_signal" ||
        node.type === "when_signal_is") &&
      node.signal === previous
        ? { ...node, signal: next }
        : node;
    if (renamed.type === "set_train_speed" || renamed.type === "set_switch" || renamed.type === "set_signal") {
      return renamed;
    }
    return { ...renamed, children: renameReferences(renamed.children, previous, next) } as AutomationNode;
  });
}
