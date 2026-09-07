import {
  currentAutomationDocument,
  parseAutomation,
  serializeAutomation,
} from "./automation-json";

it("serializes and parses a nested detector automation", () => {
  const document = parseAutomation(
    JSON.stringify({
      version: 4,
      signals: [],
      rules: [
        {
          id: "station_departure",
          enabled: true,
          root: {
            type: "train_detected",
            hub_id: "yard",
            detector_id: "D1",
            train_id: "express",
            children: [
              {
                type: "on_count",
                count: 5,
                children: [
                  {
                    type: "wait",
                    seconds: 10,
                    children: [
                      { type: "set_train_speed", speed: -35, children: [] },
                    ],
                  },
                ],
              },
            ],
          },
        },
      ],
    }),
  );

  expect(document.rules[0].root.children[0]).toMatchObject({
    type: "on_count",
    count: 5,
  });
  expect(JSON.parse(serializeAutomation(document))).toMatchObject({
    version: 4,
    signals: [],
    rules: [{ id: "station_departure" }],
  });
});

it("rejects waits outside the document range and duplicate enabled triggers", () => {
  const base = {
    version: 4,
    signals: [],
    rules: [
      {
        id: "wrong_detector",
        enabled: true,
        root: {
          type: "train_detected",
          hub_id: "yard",
          detector_id: "D2",
          train_id: "express",
          children: [
            {
              type: "wait",
              seconds: 3601,
              children: [{ type: "set_train_speed", speed: 0, children: [] }],
            },
          ],
        },
      },
    ],
  };

  expect(() => parseAutomation(JSON.stringify(base))).toThrow(
    "seconds must be a finite number from 0 to 3600",
  );
  base.rules[0].root.children[0].seconds = 20;
  base.rules.push({ ...base.rules[0], id: "duplicate" });
  expect(() => parseAutomation(JSON.stringify(base))).toThrow(
    "Only one rule for a detector and train pair may be enabled",
  );
});

it("supports an empty document", () => {
  const empty = parseAutomation('{"version":4,"signals":[],"rules":[]}');
  expect(empty).toEqual({ version: 4, signals: [], rules: [] });
  expect(JSON.parse(serializeAutomation(empty))).toEqual({ version: 4, signals: [], rules: [] });
});

it("rejects legacy documents and keeps version 4 unchanged", () => {
  expect(() => parseAutomation('{"version":3,"signals":[],"rules":[]}')).toThrow(
    "Only automation document version 4 is supported",
  );
  const current = parseAutomation('{"version":4,"signals":[],"rules":[]}');
  expect(currentAutomationDocument(current)).toBe(current);
});

it("rejects the removed count mode field", () => {
  const document = {
    version: 4,
    signals: [],
    rules: [
      {
        id: "legacy_count",
        enabled: true,
        root: {
          type: "train_detected",
          hub_id: "yard",
          detector_id: "D1",
          train_id: "express",
          children: [
            { type: "on_count", count: 2, mode: "repeat", children: [] },
          ],
        },
      },
    ],
  };

  expect(() => parseAutomation(JSON.stringify(document))).toThrow(
    "contains unknown field mode",
  );
});

it("round-trips ordered rules for multiple detectors", () => {
  const document = parseAutomation(
    JSON.stringify({
      version: 4,
      signals: [],
      rules: [
        {
          id: "d1_rule",
          enabled: true,
          root: {
            type: "train_detected",
            hub_id: "yard",
            detector_id: "D1",
            train_id: "express",
            children: [{ type: "set_train_speed", speed: 20, children: [] }],
          },
        },
        {
          id: "d2_alternative",
          enabled: false,
          root: {
            type: "train_detected",
            hub_id: "yard",
            detector_id: "D2",
            train_id: "express",
            children: [{ type: "set_train_speed", speed: -20, children: [] }],
          },
        },
      ],
    }),
  );

  expect(document.rules.map((rule) => rule.id)).toEqual(["d1_rule", "d2_alternative"]);
  expect(JSON.parse(serializeAutomation(document))).toEqual(document);
});

it("matches backend scalar and document limits", () => {
  const rule = {
    id: "limited_rule",
    enabled: true,
    root: {
      type: "train_detected",
      hub_id: " yard ",
      detector_id: " D1 ",
      train_id: " express ",
      children: [{ type: "set_train_speed", speed: 0.5, children: [] }],
    },
  };

  expect(() =>
    parseAutomation(JSON.stringify({ version: 4, signals: [], rules: [rule] })),
  ).toThrow("speed must be an integer from -100 to 100");

  rule.root.children[0].speed = 0;
  const parsed = parseAutomation(
    JSON.stringify({ version: 4, signals: [], rules: [rule] }),
  );
  expect(parsed.rules[0].root).toMatchObject({
    hub_id: "yard",
    detector_id: "D1",
    train_id: "express",
  });

  const rules = Array.from({ length: 1_001 }, (_, index) => ({
    ...rule,
    id: `rule_${index}`,
    enabled: false,
  }));
  expect(() =>
    parseAutomation(JSON.stringify({ version: 4, signals: [], rules })),
  ).toThrow("may contain at most 1000 rules");
});

it("matches backend node count and tree depth limits", () => {
  const document = (children: unknown[]) => ({
    version: 4,
    signals: [],
    rules: [
      {
        id: "bounded_tree",
        enabled: true,
        root: {
          type: "train_detected",
          hub_id: "yard",
          detector_id: "D1",
          train_id: "express",
          children,
        },
      },
    ],
  });

  const manyNodes = Array.from({ length: 1_001 }, () => ({
    type: "set_train_speed",
    speed: 0,
    children: [],
  }));
  expect(() => parseAutomation(JSON.stringify(document(manyNodes)))).toThrow(
    "Rule may contain at most 1000 nodes",
  );

  let nested: unknown = { type: "set_train_speed", speed: 0, children: [] };
  for (let depth = 0; depth < 64; depth += 1) {
    nested = { type: "wait", seconds: 1, children: [nested] };
  }
  expect(() => parseAutomation(JSON.stringify(document([nested])))).toThrow(
    "tree depth must not exceed 64",
  );
});

it("round-trips count branches", () => {
  const input = {
    version: 4,
    signals: [],
    rules: [
      {
        id: "route_fifth",
        enabled: true,
        root: {
          type: "train_detected",
          hub_id: "yard",
          detector_id: "D1",
          train_id: "express",
          children: [
            {
              type: "if_count",
              count: 5,
              children: [
                {
                  type: "branch",
                  when: "match",
                  children: [{ type: "set_train_speed", speed: 50, children: [] }],
                },
                {
                  type: "branch",
                  when: "otherwise",
                  children: [{ type: "set_train_speed", speed: 10, children: [] }],
                },
              ],
            },
          ],
        },
      },
    ],
  };

  const parsed = parseAutomation(JSON.stringify(input));
  expect(parsed).toEqual(input);
  expect(JSON.parse(serializeAutomation(parsed))).toEqual(input);
});

it("rejects malformed or misplaced branches", () => {
  const misplaced = countBranchDocument();
  const misplacedRoot = misplaced.rules[0].root as { children: unknown[] };
  misplacedRoot.children = [
    {
      type: "branch",
      when: "match",
      children: [{ type: "set_train_speed", speed: 10, children: [] }],
    },
  ];
  expect(() => parseAutomation(JSON.stringify(misplaced))).toThrow(
    "branch is only allowed directly under if_count or if_signal",
  );

  const duplicate = countBranchDocument();
  const duplicateIfCount = duplicate.rules[0].root.children[0] as {
    children: Array<{ when: string }>;
  };
  duplicateIfCount.children[1].when = "match";
  expect(() => parseAutomation(JSON.stringify(duplicate))).toThrow(
    "needs one match branch and one otherwise branch",
  );

  const empty = countBranchDocument();
  const emptyIfCount = empty.rules[0].root.children[0] as {
    children: Array<{ children: unknown[] }>;
  };
  emptyIfCount.children[0].children = [];
  expect(() => parseAutomation(JSON.stringify(empty))).toThrow(
    "needs at least one child step",
  );
});

it("round-trips signal definitions and every signal node", () => {
  const input = {
    version: 4,
    signals: ["S1"],
    rules: [
      {
        id: "signals",
        enabled: true,
        root: {
          type: "train_detected",
          hub_id: "yard",
          detector_id: "D1",
          train_id: "express",
          children: [
            { type: "set_signal", signal: "S1", value: 1, children: [] },
            {
              type: "on_signal",
              signal: "S1",
              operator: "not_eq",
              value: 0,
              children: [{ type: "set_train_speed", speed: 10, children: [] }],
            },
            {
              type: "when_signal_is",
              signal: "S1",
              operator: "more",
              value: 0,
              children: [{ type: "set_train_speed", speed: 20, children: [] }],
            },
            {
              type: "if_signal",
              signal: "S1",
              operator: "eq",
              value: 1,
              children: [
                {
                  type: "branch",
                  when: "match",
                  children: [{ type: "set_train_speed", speed: 30, children: [] }],
                },
                {
                  type: "branch",
                  when: "otherwise",
                  children: [{ type: "set_train_speed", speed: 0, children: [] }],
                },
              ],
            },
          ],
        },
      },
    ],
  };

  const parsed = parseAutomation(JSON.stringify(input));
  expect(parsed).toEqual(input);
  expect(JSON.parse(serializeAutomation(parsed))).toEqual(input);
});

it("rejects duplicate, undeclared, and unsafe signal values", () => {
  expect(() =>
    parseAutomation('{"version":4,"signals":["S1"," S1 "],"rules":[]}'),
  ).toThrow("Signal names must be unique");

  const input = countBranchDocument() as unknown as {
    signals: string[];
    rules: Array<{ root: { children: unknown[] } }>;
  };
  input.signals = ["S1"];
  const root = input.rules[0].root;
  root.children = [
    { type: "set_signal", signal: "missing", value: 1, children: [] },
  ];
  expect(() => parseAutomation(JSON.stringify(input))).toThrow(
    "signal missing is not declared",
  );

  root.children = [
    { type: "set_signal", signal: "S1", value: Number.MAX_SAFE_INTEGER + 1, children: [] },
  ];
  expect(() => parseAutomation(JSON.stringify(input))).toThrow(
    "value must be a safe integer",
  );
});

it.each([0, -1, 1.5, true])("rejects invalid count branch interval %s", (count) => {
  const input = countBranchDocument();
  const node = input.rules[0].root.children[0] as { count: unknown };
  node.count = count;

  expect(() => parseAutomation(JSON.stringify(input))).toThrow(
    "count must be a positive whole number",
  );
});

function countBranchDocument() {
  return {
    version: 4,
    signals: [],
    rules: [
      {
        id: "route_fifth",
        enabled: true,
        root: {
          type: "train_detected",
          hub_id: "yard",
          detector_id: "D1",
          train_id: "express",
          children: [
            {
              type: "if_count",
              count: 5,
              children: [
                {
                  type: "branch",
                  when: "match",
                  children: [{ type: "set_train_speed", speed: 50, children: [] }],
                },
                {
                  type: "branch",
                  when: "otherwise",
                  children: [{ type: "set_train_speed", speed: 10, children: [] }],
                },
              ],
            },
          ],
        },
      },
    ],
  };
}
