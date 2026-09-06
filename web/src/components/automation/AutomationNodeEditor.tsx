import { ActionIcon, Badge, Group, Paper, Stack, Text, Tooltip } from "@mantine/core";

import { AddStepMenu } from "./AddStepMenu";
import { createNode, type AutomationNodeType } from "./node-factories";
import { OnCountEditor } from "./nodes/OnCountEditor";
import { IfCountEditor } from "./nodes/IfCountEditor";
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
  if_count: { emoji: "🔀", label: "Count branch" },
  branch: { emoji: "↪️", label: "Branch" },
};

export function AutomationNodeList({
  nodes,
  switches,
  accessibleLabel,
  onChange,
}: {
  readonly nodes: readonly AutomationNode[];
  readonly switches: readonly SwitchOption[];
  readonly accessibleLabel: string;
  readonly onChange: (nodes: readonly AutomationNode[]) => void;
}) {
  const add = (type: AutomationNodeType) =>
    onChange([...nodes, createNode(type, switches)]);

  return (
    <Stack gap="xs" role="group" aria-label={accessibleLabel}>
      {nodes.length > 0 && (
        <ol className={classes.nodeList}>
          {nodes.map((node, index) => (
            <AutomationNodeEditor
              key={`${index}-${node.type}`}
              node={node}
              index={index}
              count={nodes.length}
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
  switches,
  onChange,
  onRemove,
  onMove,
}: {
  readonly node: AutomationNode;
  readonly index: number;
  readonly count: number;
  readonly switches: readonly SwitchOption[];
  readonly onChange: (node: AutomationNode) => void;
  readonly onRemove: () => void;
  readonly onMove: (offset: -1 | 1) => void;
}) {
  const hasChildren = node.type === "wait" || node.type === "on_count";
  const heading = NODE_LABELS[node.type];

  return (
    <li className={classes.nodeItem}>
      <Paper withBorder radius="lg" p="sm" className={classes.nodeCard}>
        <Stack gap="sm">
          <Group justify="space-between" align="center" wrap="wrap">
            <Group gap="xs" wrap="nowrap">
              <Badge variant="filled" color={hasChildren ? "violet" : "blue"} circle size="md">
                {index + 1}
              </Badge>
              <Text className={classes.stepEmoji} aria-hidden>{heading.emoji}</Text>
              <Text fw={800} size="sm">{heading.label}</Text>
            </Group>
            <Group gap={6} wrap="nowrap">
              <Tooltip label="Move up">
                <ActionIcon
                  variant="light"
                  color="gray"
                  size="md"
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
                  size="md"
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
                  size="md"
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
          {node.type === "if_count" && <IfCountEditor node={node} onChange={onChange} />}

          {hasChildren && (
            <div className={classes.children}>
              <Text className={classes.thenArrow} aria-hidden>👇</Text>
              <AutomationNodeList
                nodes={node.children}
                switches={switches}
                accessibleLabel={`Steps after ${heading.label} step ${index + 1}`}
                onChange={(children) => onChange({ ...node, children })}
              />
            </div>
          )}
          {node.type === "if_count" && (
            <Stack gap="sm" className={classes.branchGroup}>
              {node.children.map((branch, branchIndex) => (
                <Paper
                  withBorder
                  radius="md"
                  p="sm"
                  key={branch.when}
                  className={classes.branchCard}
                >
                  <Stack gap="xs">
                    <Text fw={700} size="sm">
                      {branch.when === "match"
                        ? `Every ${node.count}${ordinalSuffix(node.count)} time`
                        : "All other times"}
                    </Text>
                    <AutomationNodeList
                      nodes={branch.children}
                      switches={switches}
                      accessibleLabel={
                        branch.when === "match"
                          ? "Steps every configured count"
                          : "Steps all other times"
                      }
                      onChange={(children) => {
                        const branches = [...node.children] as [
                          typeof node.children[0],
                          typeof node.children[1],
                        ];
                        branches[branchIndex] = { ...branch, children };
                        onChange({ ...node, children: branches });
                      }}
                    />
                  </Stack>
                </Paper>
              ))}
            </Stack>
          )}
        </Stack>
      </Paper>
    </li>
  );
}

function ordinalSuffix(value: number): string {
  const remainder100 = value % 100;
  if (remainder100 >= 11 && remainder100 <= 13) return "th";
  switch (value % 10) {
    case 1:
      return "st";
    case 2:
      return "nd";
    case 3:
      return "rd";
    default:
      return "th";
  }
}
