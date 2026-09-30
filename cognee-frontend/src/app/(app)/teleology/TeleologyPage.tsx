"use client";

import { useEffect, useRef, useState } from "react";
import { TrackPageView } from "@/modules/analytics";
import { useBusinessLanguage } from "@/modules/business/BusinessLanguageContext";
import { useCogniInstance } from "@/modules/tenant/TenantProvider";
import { useFilter } from "@/ui/layout/FilterContext";
import PageLoading from "@/ui/elements/PageLoading";
import OntologyBrowser from "./browser/OntologyBrowser";
import TeleologyClassicPage from "./TeleologyClassicPage";
import "./browser/ontology.css";

const MODE_KEY = "cognee.teleology.uiMode";

export default function TeleologyPage() {
  const { language } = useBusinessLanguage();
  const { cogniInstance, isInitializing } = useCogniInstance();
  const { datasets, selectedDataset, setSelectedDataset, loading: datasetsLoading } = useFilter();
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"browser" | "classic">("browser");
  const [toolbarCollapsed, setToolbarCollapsed] = useState(false);
  const datasetDefaulted = useRef(false);

  useEffect(() => {
    try { if (window.localStorage.getItem(MODE_KEY) === "classic") setMode("classic"); } catch { /* ignore */ }
  }, []);

  function switchMode(next: "browser" | "classic") {
    setMode(next);
    setToolbarCollapsed(false);
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
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, height: "100%", background: "transparent" }}>
      <TrackPageView page="teleology" />
      <div className="teleology-toolbar">
        <div className="teleology-toolbar-row teleology-toolbar-top">
          <div className="teleology-mode-tabs">
            <button type="button" className={`teleology-mode-tab${mode === "browser" ? " is-active" : ""}`} aria-pressed={mode === "browser"} onClick={() => switchMode("browser")}>{zh ? "目标层级" : "Goal hierarchy"}</button>
            <button type="button" className={`teleology-mode-tab${mode === "classic" ? " is-active" : ""}`} aria-pressed={mode === "classic"} onClick={() => switchMode("classic")}>{zh ? "目的关系" : "Purpose relations"}</button>
          </div>
          <div className="teleology-toolbar-view-actions">
            <button
              type="button"
              className="onto-btn onto-collapse-btn"
              aria-expanded={!toolbarCollapsed}
              aria-controls="teleology-toolbar-data-row"
              onClick={() => setToolbarCollapsed((collapsed) => !collapsed)}
            >
              {toolbarCollapsed ? (zh ? "展开 ↓" : "Expand ↓") : (zh ? "收起 ↑" : "Collapse ↑")}
            </button>
          </div>
        </div>
        <div id="teleology-toolbar-data-row" className="teleology-toolbar-row teleology-toolbar-bottom" style={{ display: toolbarCollapsed ? "none" : undefined }}>
          {mode === "browser"
            ? <div id="teleology-browser-data-actions" className="teleology-toolbar-data-actions" />
            : <div id="teleology-classic-info" className="teleology-toolbar-data-actions" />}
        </div>
      </div>
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
          />
        ) : <TeleologyClassicPage />}
      </div>
    </div>
  );
}
