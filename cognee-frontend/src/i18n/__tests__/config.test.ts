import { DEFAULT_LOCALE, isLocale, resolveLocale } from "@/i18n/config";

describe("locale configuration", () => {
  it("uses Simplified Chinese when a preference is missing or invalid", () => {
    expect(DEFAULT_LOCALE).toBe("zh-CN");
    expect(resolveLocale(undefined)).toBe("zh-CN");
    expect(resolveLocale("fr")).toBe("zh-CN");
  });

  it("only accepts the locales served by the application", () => {
    expect(isLocale("zh-CN")).toBe(true);
    expect(isLocale("en")).toBe(true);
    expect(isLocale("zh")).toBe(false);
  });
});
