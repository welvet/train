import { ActionIcon, Badge, Group, Paper, Stack, Text, Tooltip } from "@mantine/core";

import { AddStepMenu } from "./AddStepMenu";
import { createNode, type AutomationNodeType } from "./node-factories";
import { OnCountEditor } from "./nodes/OnCountEditor";
import { SetSwitchEditor } from "./nodes/SetSwitchEditor";
import { SetTrainSpeedEditor } from "./nodes/SetTrainSpeedEditor";
import { WaitEditor } from "./nodes/WaitEditor";
import type { AutomationNode, SwitchOption } from "./types";
import classes from "./automation.module.css";

const NODE_LABELS: Record<AutomationNode["type"], { emoji: string; label: string }> = {
  set_switch: { emoji: "🚦", label: "Switch" },
  wait: { emoji: "⏱️", label: "Wait" },
  set_train_speed: { emoji: "🚂", label: "Speed" },
  on_count: { emoji: "🔁", label: "Count" },
};

export function AutomationNodeList({
  nodes,
  switches,
  allowEmpty = false,
  onChange,
}: {
  readonly nodes: readonly AutomationNode[];
  readonly switches: readonly SwitchOption[];
  readonly allowEmpty?: boolean;
  readonly onChange: (nodes: readonly AutomationNode[]) => void;
}) {
  const add = (type: AutomationNodeType) =>
    onChange([...nodes, createNode(type, switches)]);

  return (
    <Stack gap="xs">
      {nodes.length > 0 && (
        <ol className={classes.nodeList}>
          {nodes.map((node, index) => (
            <AutomationNodeEditor
              key={`${index}-${node.type}`}
              node={node}
              index={index}
              count={nodes.length}
              allowEmpty={allowEmpty}
              switches={switches}
              onChange={(next) =>
                onChange(nodes.map((item, itemIndex) => (itemIndex === index ? next : item)))
              }
              onRemove={() => onChange(nodes.filter((_, itemIndex) => itemIndex !== index))}
              onMove={(offset) => {
                const target = index + offset;
                if (target < 0 || target >= nodes.length) return;
                const next = [...nodes];
                [next[index], next[target]] = [next[target], next[index]];
                onChange(next);
              }}
            />
          ))}
        </ol>
      )}
      <AddStepMenu onAdd={add} hasSwitches={switches.length > 0} />
    </Stack>
  );
}

function AutomationNodeEditor({
  node,
  index,
  count,
  allowEmpty,
  switches,
  onChange,
  onRemove,
  onMove,
}: {
  readonly node: AutomationNode;
  readonly index: number;
  readonly count: number;
  readonly allowEmpty: boolean;
  readonly switches: readonly SwitchOption[];
  readonly onChange: (node: AutomationNode) => void;
  readonly onRemove: () => void;
  readonly onMove: (offset: -1 | 1) => void;
}) {
  const hasChildren = node.type === "wait" || node.type === "on_count";
  const heading = NODE_LABELS[node.type];

  return (
    <li className={classes.nodeItem}>
      <Paper withBorder radius="lg" p={{ base: "sm", sm: "md" }} className={classes.nodeCard}>
        <Stack gap="md">
          <Group justify="space-between" align="center" wrap="nowrap">
            <Group gap="xs" wrap="nowrap">
              <Badge variant="filled" color={hasChildren ? "violet" : "blue"} circle size="lg">
                {index + 1}
              </Badge>
              <Text className={classes.stepEmoji} aria-hidden>{heading.emoji}</Text>
              <Text fw={800}>{heading.label}</Text>
            </Group>
            <Group gap={6} wrap="nowrap">
              <Tooltip label="Move up">
                <ActionIcon
                  variant="light"
                  color="gray"
                  size="lg"
                  disabled={index === 0}
                  aria-label={`Move ${heading.label} step ${index + 1} up`}
                  onClick={() => onMove(-1)}
                >
                  ⬆️
                </ActionIcon>
              </Tooltip>
              <Tooltip label="Move down">
                <ActionIcon
                  variant="light"
                  color="gray"
                  size="lg"
                  disabled={index === count - 1}
                  aria-label={`Move ${heading.label} step ${index + 1} down`}
                  onClick={() => onMove(1)}
                >
                  ⬇️
                </ActionIcon>
              </Tooltip>
              <Tooltip label="Remove">
                <ActionIcon
                  variant="light"
                  color="red"
                  size="lg"
                  disabled={count === 1 && !allowEmpty}
                  aria-label={`Remove ${heading.label} step ${index + 1}`}
                  onClick={onRemove}
                >
                  🗑️
                </ActionIcon>
              </Tooltip>
            </Group>
          </Group>

          {node.type === "set_train_speed" && (
            <SetTrainSpeedEditor node={node} onChange={onChange} />
          )}
          {node.type === "set_switch" && (
            <SetSwitchEditor node={node} switches={switches} onChange={onChange} />
          )}
          {node.type === "wait" && <WaitEditor node={node} onChange={onChange} />}
          {node.type === "on_count" && <OnCountEditor node={node} onChange={onChange} />}

          {hasChildren && (
            <div className={classes.children}>
              <Text className={classes.thenArrow} aria-hidden>👇</Text>
              <AutomationNodeList
                nodes={node.children}
                switches={switches}
                onChange={(children) => onChange({ ...node, children })}
              />
            </div>
          )}
        </Stack>
      </Paper>
    </li>
  );
}
