import { parseAutomation, serializeAutomation } from "./automation-json";

it("serializes and parses a nested detector automation", () => {
  const document = parseAutomation(
    JSON.stringify({
      version: 1,
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
    version: 1,
    rules: [{ id: "station_departure" }],
  });
});

it("rejects waits outside the document range and duplicate enabled triggers", () => {
  const base = {
    version: 1,
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
  const empty = parseAutomation('{"version":1,"rules":[]}');
  expect(empty).toEqual({ version: 1, rules: [] });
  expect(JSON.parse(serializeAutomation(empty))).toEqual({ version: 1, rules: [] });
});

it("rejects the removed count mode field", () => {
  const document = {
    version: 1,
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
      version: 1,
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
    parseAutomation(JSON.stringify({ version: 1, rules: [rule] })),
  ).toThrow("speed must be an integer from -100 to 100");

  rule.root.children[0].speed = 0;
  const parsed = parseAutomation(
    JSON.stringify({ version: 1, rules: [rule] }),
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
    parseAutomation(JSON.stringify({ version: 1, rules })),
  ).toThrow("may contain at most 1000 rules");
});

it("matches backend node count and tree depth limits", () => {
  const document = (children: unknown[]) => ({
    version: 1,
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
