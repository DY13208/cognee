import { formatDate, formatRelativeTime } from "@/utils/formatDate";
import { timeAgo } from "@/utils/timeAgo";

describe("formatDate locale", () => {
  it("produces different calendar strings for Simplified Chinese and English", () => {
    const iso = "2026-03-15T08:30:00Z";
    expect(formatDate(iso, "zh-CN")).not.toBe(formatDate(iso, "en"));
  });

  it("formats relative time with the active locale", () => {
    const iso = new Date(Date.now() - 90_000).toISOString();
    expect(formatRelativeTime(iso, "en")).toMatch(/minute/i);
    expect(formatRelativeTime(iso, "zh-CN")).toMatch(/分钟/);
  });
});

describe("timeAgo locale", () => {
  it("delegates to formatRelativeTime for the active locale", () => {
    const iso = new Date(Date.now() - 90_000).toISOString();
    expect(timeAgo(iso, "en")).toBe(formatRelativeTime(iso, "en"));
    expect(timeAgo(iso, "zh-CN")).toBe(formatRelativeTime(iso, "zh-CN"));
    expect(timeAgo(iso, "en")).not.toBe(timeAgo(iso, "zh-CN"));
  });
});
