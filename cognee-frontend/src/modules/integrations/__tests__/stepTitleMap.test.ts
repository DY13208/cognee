import { translateStepText } from "../stepTitleMap";

describe("translateStepText", () => {
  const t = (key: string) => `zh:${key}`;

  it("maps known wizard titles onto catalogue keys", () => {
    expect(translateStepText("Install the Cognee plugin", t)).toBe("zh:installPlugin");
    expect(translateStepText("You're all set", t)).toBe("zh:allSet");
    expect(translateStepText("Option A · Your existing memory", t)).toBe("zh:optionExistingMemory");
  });

  it("leaves product-specific unmatched strings unchanged", () => {
    expect(translateStepText("Claude Code", t)).toBe("Claude Code");
  });
});
