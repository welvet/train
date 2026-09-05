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
                mode: "repeat",
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
    mode: "repeat",
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
