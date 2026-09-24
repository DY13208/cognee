"use client";

import { useBusinessLanguage } from "@/modules/business/BusinessLanguageContext";

export default function LanguageSwitch() {
  const { language, setLanguage } = useBusinessLanguage();
  const next = language === "zh" ? "en" : "zh";
  const label = language === "zh" ? "中" : "EN";
  const ariaLabel = language === "zh" ? "切换到 English" : "Switch to 中文";

  return (
    <button
      type="button"
      className="business-language-switch"
      aria-label={ariaLabel}
      title={ariaLabel}
      lang={language === "zh" ? "zh-CN" : "en"}
      onClick={() => setLanguage(next)}
    >
      <span data-lang={language}>{label}</span>
    </button>
  );
}
