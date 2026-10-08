"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { TrackPageView } from "@/modules/analytics";
import { useBusinessLanguage } from "@/modules/business/BusinessLanguageContext";
import { useCogniInstance } from "@/modules/tenant/TenantProvider";
import { useFilter } from "@/ui/layout/FilterContext";
import PageLoading from "@/ui/elements/PageLoading";
import OntologyBrowser from "./browser/OntologyBrowser";
import TeleologyClassicPage from "./TeleologyClassicPage";
import GoalNetworkView from "./browser/GoalNetworkView";
import "./browser/ontology.css";

const MODE_KEY = "cognee.teleology.uiMode";

export default function TeleologyPage() {
  const { language } = useBusinessLanguage();
  const { cogniInstance, isInitializing } = useCogniInstance();
  const { datasets, selectedDataset, setSelectedDataset, loading: datasetsLoading } = useFilter();
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"network" | "browser" | "classic">("network");
  const datasetDefaulted = useRef(false);
  const [navigationHost, setNavigationHost] = useState<HTMLElement | null>(null);
  useEffect(() => { setNavigationHost(document.getElementById("teleology-navigation-slot")); }, []);

  function switchMode(next: "network" | "browser" | "classic") {
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
  const navigation = (<nav className="teleology-view-navigation" aria-label={zh ? "目的论视图" : "Teleology views"}>
        <div className="teleology-mode-tabs">
            <button type="button" className={`teleology-mode-tab${mode === "network" ? " is-active" : ""}`} aria-pressed={mode === "network"} onClick={() => switchMode("network")}>经营网络</button>
            <button type="button" className={`teleology-mode-tab${mode === "browser" ? " is-active" : ""}`} aria-pressed={mode === "browser"} onClick={() => switchMode("browser")}>{zh ? "目标层级" : "Goal hierarchy"}</button>
            <button type="button" className={`teleology-mode-tab${mode === "classic" ? " is-active" : ""}`} aria-pressed={mode === "classic"} onClick={() => switchMode("classic")}>{zh ? "目的关系" : "Purpose relations"}</button>
        </div>
      </nav>);

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, height: "100%", background: "transparent" }}>
      <TrackPageView page="teleology" />
      {navigationHost ? createPortal(navigation, navigationHost) : navigation}
      <div className="teleology-toolbar">
        <div id="teleology-toolbar-data-row" className="teleology-toolbar-row teleology-toolbar-bottom">
          <div id="teleology-toolbar-context" className="teleology-toolbar-context">
            {mode === "network" ? <span className="network-muted">{selectedDataset?.name || "请选择数据集"} · 经营关系网络</span> : mode === "browser"
              ? <div id="teleology-browser-data-actions" className="teleology-toolbar-data-actions" />
              : <div id="teleology-classic-info" className="teleology-toolbar-data-actions" />}
          </div>
        </div>
      </div>
      <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        {mode === "network" ? <GoalNetworkView onShowHierarchy={() => switchMode("browser")} instance={cogniInstance} datasetId={selectedDataset?.id || datasets[0]?.id || ""} /> : mode === "browser" ? (
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
