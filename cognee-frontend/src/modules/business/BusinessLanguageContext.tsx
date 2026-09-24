"use client";

import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useState,
  type ReactNode,
} from "react";

export type BusinessLanguage = "zh" | "en";

const STORAGE_KEY = "cognee-language";
const LEGACY_STORAGE_KEY = "cognee-business-language";
const BusinessLanguageContext = createContext<{
  language: BusinessLanguage;
  setLanguage: (language: BusinessLanguage) => void;
}>({ language: "zh", setLanguage: () => {} });

function readStoredLanguage(): BusinessLanguage {
  const saved =
    window.localStorage.getItem(STORAGE_KEY) ??
    window.localStorage.getItem(LEGACY_STORAGE_KEY);
  return saved === "zh" || saved === "en" ? saved : "zh";
}

export function t(language: BusinessLanguage, en: string, zh: string): string {
  return language === "zh" ? zh : en;
}

export function BusinessLanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<BusinessLanguage>("zh");
  const [ready, setReady] = useState(false);

  // Read before paint so a stored "en" preference does not flash Chinese UI.
  useLayoutEffect(() => {
    const saved = readStoredLanguage();
    setLanguage(saved);
    setReady(true);
    if (window.localStorage.getItem(LEGACY_STORAGE_KEY) && !window.localStorage.getItem(STORAGE_KEY)) {
      window.localStorage.setItem(STORAGE_KEY, saved);
      window.localStorage.removeItem(LEGACY_STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    if (ready) window.localStorage.setItem(STORAGE_KEY, language);
  }, [language, ready]);

  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  }, [language]);

  return (
    <BusinessLanguageContext.Provider value={{ language, setLanguage }}>
      {children}
    </BusinessLanguageContext.Provider>
  );
}

export function useBusinessLanguage() {
  return useContext(BusinessLanguageContext);
}
