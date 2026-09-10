"use client";

import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { LOCALE_COOKIE_NAME, SUPPORTED_LOCALES, type Locale } from "@/i18n/config";

const COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365;

function localeLabel(locale: Locale, translate: ReturnType<typeof useTranslations>): string {
  return locale === "zh-CN" ? translate("chinese") : translate("english");
}

/** Persists a language preference and re-renders the current App Router route. */
export default function LanguageSwitcher({ compact = false }: { compact?: boolean }) {
  const locale = useLocale() as Locale;
  const t = useTranslations("LanguageSwitcher");
  const router = useRouter();

  function changeLocale(nextLocale: Locale): void {
    document.cookie = `${LOCALE_COOKIE_NAME}=${encodeURIComponent(nextLocale)}; Path=/; Max-Age=${COOKIE_MAX_AGE_SECONDS}; SameSite=Lax`;
    document.documentElement.lang = nextLocale;
    router.refresh();
  }

  return (
    <label title={compact ? t("label") : undefined} style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 7, width: "100%", color: "rgba(237,236,234,0.35)", fontSize: 12.5, fontWeight: 500 }}>
      {!compact && <span>{t("label")}</span>}
      <select aria-label={t("label")} value={locale} onChange={(event) => changeLocale(event.target.value as Locale)} style={{ minWidth: compact ? 42 : 100, padding: "5px 6px", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 6, background: "rgba(255,255,255,0.06)", color: "inherit", font: "inherit", cursor: "pointer" }}>
        {SUPPORTED_LOCALES.map((supportedLocale) => (
          <option key={supportedLocale} value={supportedLocale} style={{ color: "#1e1e1c" }}>
            {localeLabel(supportedLocale, t)}
          </option>
        ))}
      </select>
    </label>
  );
}
