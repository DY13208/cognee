import { getRequestConfig } from "next-intl/server";
import { getMessages } from "./getMessages";
import { getRequestLocale } from "./getRequestLocale";

/** Request-scoped next-intl config. Locale still comes from the Cookie, not a URL prefix. */
export default getRequestConfig(async () => {
  const locale = await getRequestLocale();
  return {
    locale,
    messages: getMessages(locale),
  };
});
