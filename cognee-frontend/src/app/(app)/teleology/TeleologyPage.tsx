"use client";

import { useEffect, useState } from "react";
import { TrackPageView } from "@/modules/analytics";
import { useBusinessLanguage } from "@/modules/business/BusinessLanguageContext";
import { useCogniInstance } from "@/modules/tenant/TenantProvider";
import { useFilter } from "@/ui/layout/FilterContext";
import PageLoading from "@/ui/elements/PageLoading";
import OntologyBrowser from "./browser/OntologyBrowser";
import TeleologyClassicPage from "./TeleologyClassicPage";

type UiMode = "browser" | "classic";

const MODE_KEY = "cognee.teleology.uiMode";

export default function TeleologyPage() {
  const { language } = useBusinessLanguage();
  const { cogniInstance, isInitializing } = useCogniInstance();
  const { datasets, selectedDataset, setSelectedDataset, loading: datasetsLoading } = useFilter();
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<UiMode>("browser");

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(MODE_KEY);
      if (saved === "classic" || saved === "browser") setMode(saved);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!cogniInstance || isInitializing || datasetsLoading) return;
    if (!selectedDataset && datasets[0]) setSelectedDataset(datasets[0]);
  }, [cogniInstance, isInitializing, datasetsLoading, datasets, selectedDataset, setSelectedDataset]);

  function switchMode(next: UiMode) {
    setMode(next);
    try {
      window.localStorage.setItem(MODE_KEY, next);
    } catch {
      /* ignore */
    }
  }

  if (isInitializing || datasetsLoading || !cogniInstance) {
    return <PageLoading name={language === "zh" ? "目的论" : "Teleology"} />;
  }

  const zh = language === "zh";

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, height: "100%" }}>
      <TrackPageView page="teleology" />
      <div
        style={{
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "8px 16px",
          borderBottom: "1px solid rgba(255,255,255,0.08)",
          background: "#121214",
        }}
      >
        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", color: "rgba(232,231,228,0.4)" }}>
          {zh ? "视图模式" : "VIEW MODE"}
        </span>
        <div
          style={{
            display: "inline-flex",
            borderRadius: 8,
            border: "1px solid rgba(255,255,255,0.12)",
            overflow: "hidden",
          }}
        >
          <button
            type="button"
            onClick={() => switchMode("browser")}
            style={{
              border: "none",
              padding: "7px 12px",
              fontSize: 12,
              fontWeight: 650,
              cursor: "pointer",
              fontFamily: "inherit",
              background: mode === "browser" ? "rgba(124,140,255,0.2)" : "transparent",
              color: mode === "browser" ? "#E8E7E4" : "rgba(232,231,228,0.5)",
            }}
          >
            {zh ? "企业浏览器" : "Enterprise browser"}
          </button>
          <button
            type="button"
            onClick={() => switchMode("classic")}
            style={{
              border: "none",
              borderLeft: "1px solid rgba(255,255,255,0.1)",
              padding: "7px 12px",
              fontSize: 12,
              fontWeight: 650,
              cursor: "pointer",
              fontFamily: "inherit",
              background: mode === "classic" ? "rgba(124,140,255,0.2)" : "transparent",
              color: mode === "classic" ? "#E8E7E4" : "rgba(232,231,228,0.5)",
            }}
          >
            {zh ? "经典力导向" : "Classic force graph"}
          </button>
        </div>
        <span style={{ fontSize: 11, color: "rgba(232,231,228,0.35)", marginLeft: 4 }}>
          {mode === "browser"
            ? zh
              ? "卡片 · Focus 邻域 · 对齐你的设计稿"
              : "Cards · focus neighbourhood · design mock"
            : zh
              ? "原圆环节点自由布局"
              : "Original circular force layout"}
        </span>
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
        ) : (
          <TeleologyClassicPage />
        )}
      </div>
    </div>
  );
}
