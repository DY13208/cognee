export const SUPPORTED_LOCALES = ["zh-CN", "en"] as const;

export type Locale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "zh-CN";
export const LOCALE_COOKIE_NAME = "cognee_locale";

export function isLocale(value: string | undefined): value is Locale {
  return value !== undefined && SUPPORTED_LOCALES.includes(value as Locale);
}

/** Resolve an untrusted persisted value to a supported application locale. */
export function resolveLocale(value: string | undefined): Locale {
  return isLocale(value) ? value : DEFAULT_LOCALE;
}
