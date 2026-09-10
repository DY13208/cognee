/**
 * Coarse "how long ago" for timestamps shown next to live state.
 *
 * Lived in AgentActivityTerminal, a 991-line client component. Importing eight
 * lines of arithmetic from there pulled the whole terminal into any page that
 * wanted a relative time, so it moved out; that module re-exports it and its
 * callers are unchanged.
 */
import { DEFAULT_LOCALE, type Locale } from "@/i18n/config";
import { formatRelativeTime } from "./formatDate";

export function timeAgo(dateStr: string, locale: Locale = DEFAULT_LOCALE): string {
  return formatRelativeTime(dateStr, locale);
}
