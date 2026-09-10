import "server-only";

import { cookies } from "next/headers";
import { LOCALE_COOKIE_NAME, resolveLocale, type Locale } from "./config";

/** Read the user's language preference without adding a locale segment to URLs. */
export async function getRequestLocale(): Promise<Locale> {
  const cookieStore = await cookies();
  return resolveLocale(cookieStore.get(LOCALE_COOKIE_NAME)?.value);
}
