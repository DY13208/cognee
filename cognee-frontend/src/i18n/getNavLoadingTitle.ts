import "server-only";

import { getMessages } from "./getMessages";
import { getRequestLocale } from "./getRequestLocale";

type NavItemKey =
  | "overview"
  | "brain"
  | "search"
  | "sessions"
  | "integrations"
  | "settings"
  | "apiKeys"
  | "mindmap";

export async function getNavLoadingTitle(item: NavItemKey): Promise<string> {
  const locale = await getRequestLocale();
  const messages = getMessages(locale) as { navigation: { items: Record<string, string> } };
  return messages.navigation.items[item];
}
