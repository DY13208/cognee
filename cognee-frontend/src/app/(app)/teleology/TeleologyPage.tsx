"use client";

import { useEffect, useRef, useState } from "react";
import { TrackPageView } from "@/modules/analytics";
import { useBusinessLanguage } from "@/modules/business/BusinessLanguageContext";
import { useCogniInstance } from "@/modules/tenant/TenantProvider";
import { useFilter } from "@/ui/layout/FilterContext";
import PageLoading from "@/ui/elements/PageLoading";
import GoalModelPage from "./browser/GoalModelPage";
import TeleologyClassicPage from "./TeleologyClassicPage";
import "./browser/ontology.css";

const MODE_KEY = "cognee.teleology.uiMode";

export default function TeleologyPage() {
  const { language } = useBusinessLanguage();
  const { cogniInstance, isInitializing } = useCogniInstance();
  const { datasets, selectedDataset, setSelectedDataset, loading: datasetsLoading } = useFilter();
  const [mode, setMode] = useState<"browser" | "classic">("browser");
  const datasetDefaulted = useRef(false);

  useEffect(() => {
    try { if (window.localStorage.getItem(MODE_KEY) === "classic") setMode("classic"); } catch { /* ignore */ }
  }, []);

  function switchMode(next: "browser" | "classic") {
    setMode(next);
    try { window.localStorage.setItem(MODE_KEY, next); } catch { /* ignore */ }
  }

  useEffect(() => {
    if (!cogniInstance || isInitializing || datasetsLoading || datasetDefaulted.current || datasets.length === 0) return;
    datasetDefaulted.current = true;
    const preferred = datasets.find((dataset) => dataset.name.trim().toLowerCase() === "yiran_cpd");
    if (preferred) {
      if (selectedDataset?.id !== preferred.id) setSelectedDataset(preferred);
      return;
    }
    if (!selectedDataset && datasets[0]) setSelectedDataset(datasets[0]);
  }, [cogniInstance, isInitializing, datasetsLoading, datasets, selectedDataset, setSelectedDataset]);

  if (isInitializing || datasetsLoading || !cogniInstance) {
    return <PageLoading name={language === "zh" ? "目的论" : "Teleology"} />;
  }

  const zh = language === "zh";

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, height: "100%", background: "#0e0e10" }}>
      <TrackPageView page="teleology" />
      <div className="teleology-mode-bar">
        <div className="teleology-mode-tabs">
          <button type="button" className={`teleology-mode-tab${mode === "browser" ? " is-active" : ""}`} aria-pressed={mode === "browser"} onClick={() => switchMode("browser")}>{zh ? "AI 目标模型" : "AI Goal Model"}</button>
          <button type="button" className={`teleology-mode-tab${mode === "classic" ? " is-active" : ""}`} aria-pressed={mode === "classic"} onClick={() => switchMode("classic")}>{zh ? "目的关系" : "Purpose relations"}</button>
        </div>
        <div id="teleology-classic-actions" className="teleology-classic-actions" />
      </div>
      <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        {mode === "browser" ? (
          <GoalModelPage
            instance={cogniInstance}
            datasetId={selectedDataset?.id || datasets[0]?.id || ""}
            datasetName={selectedDataset?.name || datasets[0]?.name || ""}
            language={zh ? "zh" : "en"}
          />
        ) : <TeleologyClassicPage />}
      </div>
    </div>
  );
}
