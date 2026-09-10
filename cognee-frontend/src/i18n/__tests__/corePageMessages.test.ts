import en from "../messages/en.json";
import zhCN from "../messages/zh-CN.json";

function keys(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return [prefix];
  return Object.entries(value).flatMap(([key, child]) => keys(child, prefix ? `${prefix}.${key}` : key));
}

describe("core page message catalogs", () => {
  it.each(["datasets", "search", "sessions", "navigation", "apiKeys", "integrations", "settings", "dashboard", "skills", "knowledgeGraph", "graphModels", "survey", "waitlist", "common"] as const)("keeps %s keys aligned across locales", (namespace) => {
    expect(keys(en[namespace]).sort()).toEqual(keys(zhCN[namespace]).sort());
  });
});
