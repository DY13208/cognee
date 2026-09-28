"use client";

import { useEffect, useState } from "react";
import { TrackPageView } from "@/modules/analytics";
import { useBusinessLanguage } from "@/modules/business/BusinessLanguageContext";
import { useCogniInstance } from "@/modules/tenant/TenantProvider";
import { useFilter } from "@/ui/layout/FilterContext";
import PageLoading from "@/ui/elements/PageLoading";
import OntologyBrowser from "./browser/OntologyBrowser";
import TeleologyClassicPage from "./TeleologyClassicPage";

const MODE_KEY = "cognee.teleology.uiMode";

export default function TeleologyPage() {
  const { language } = useBusinessLanguage();
  const { cogniInstance, isInitializing } = useCogniInstance();
  const { datasets, selectedDataset, setSelectedDataset, loading: datasetsLoading } = useFilter();
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"browser" | "classic">("browser");
  const [browserHeaderCollapsed, setBrowserHeaderCollapsed] = useState(false);

  useEffect(() => {
    try { if (window.localStorage.getItem(MODE_KEY) === "classic") setMode("classic"); } catch { /* ignore */ }
  }, []);

  function switchMode(next: "browser" | "classic") {
    setMode(next);
    try { window.localStorage.setItem(MODE_KEY, next); } catch { /* ignore */ }
  }

  useEffect(() => {
    if (!cogniInstance || isInitializing || datasetsLoading) return;
    if (!selectedDataset && datasets[0]) setSelectedDataset(datasets[0]);
  }, [cogniInstance, isInitializing, datasetsLoading, datasets, selectedDataset, setSelectedDataset]);

  if (isInitializing || datasetsLoading || !cogniInstance) {
    return <PageLoading name={language === "zh" ? "目的论" : "Teleology"} />;
  }

  const zh = language === "zh";

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, height: "100%" }}>
      <TrackPageView page="teleology" />
      {!(mode === "browser" && browserHeaderCollapsed) && <div className="teleology-mode-bar">
        <button type="button" className={`teleology-mode-tab${mode === "browser" ? " is-active" : ""}`} aria-pressed={mode === "browser"} onClick={() => switchMode("browser")}>{zh ? "目标层级" : "Goal hierarchy"}</button>
        <button type="button" className={`teleology-mode-tab${mode === "classic" ? " is-active" : ""}`} aria-pressed={mode === "classic"} onClick={() => switchMode("classic")}>{zh ? "目的关系" : "Purpose relations"}</button>
      </div>}
      <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        {mode === "browser" ? (
          <OntologyBrowser
            instance={cogniInstance}
            datasets={datasets.map((d) => ({ id: d.id, name: d.name }))}
            selectedDataset={
              selectedDataset
                ? { id: selectedDataset.id, name: selectedDataset.name }
                : datasets[0]
                  ? { id: datasets[0].id, name: datasets[0].name }
                  : null
            }
            onSelectDataset={(d) => {
              const full = datasets.find((x) => x.id === d.id);
              if (full) setSelectedDataset(full);
            }}
            language={zh ? "zh" : "en"}
            busy={busy}
            onBusy={setBusy}
            onHeaderCollapsedChange={setBrowserHeaderCollapsed}
          />
        ) : <TeleologyClassicPage />}
      </div>
    </div>
  );
}
