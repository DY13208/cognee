import "server-only";

import type { AbstractIntlMessages } from "next-intl";
import type { Locale } from "./config";
import en from "./messages/en.json";
import zhCN from "./messages/zh-CN.json";

const messagesByLocale: Record<Locale, AbstractIntlMessages> = {
  en,
  "zh-CN": zhCN,
};

export function getMessages(locale: Locale): AbstractIntlMessages {
  return messagesByLocale[locale];
}
