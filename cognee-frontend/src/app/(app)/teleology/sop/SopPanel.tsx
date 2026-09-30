"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useBusinessLanguage } from "@/modules/business/BusinessLanguageContext";
import { useCogniInstance } from "@/modules/tenant/TenantProvider";
import { useFilter } from "@/ui/layout/FilterContext";
import { generateSopProposal } from "@/modules/teleology/sop/sopClient";
import SopViewer from "./SopViewer";
import "./sop.css";

const STORAGE_KEY = "cognee.sop.proposal";

export default function SopPanel() {
  const { language } = useBusinessLanguage();
  const { cogniInstance } = useCogniInstance();
  const { selectedDataset, datasets } = useFilter();
  const zh = language === "zh";
  const datasetId = selectedDataset?.id || datasets[0]?.id || "";
  const [proposal, setProposal] = useState<Record<string, unknown> | null>(null);
  const [roomKey, setRoomKey] = useState("");
  const [nodeUid, setNodeUid] = useState("");
  const [contextText, setContextText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    try {
      const stored = window.sessionStorage.getItem(STORAGE_KEY);
      if (stored) setProposal(JSON.parse(stored));
    } catch { /* ignore a stale handoff */ }
    function onProposal(event: Event) {
      const detail = (event as CustomEvent).detail;
      if (detail && typeof detail === "object" && detail.proposal) setProposal(detail.proposal);
    }
    window.addEventListener("cognee:sop-proposal", onProposal);
    return () => window.removeEventListener("cognee:sop-proposal", onProposal);
  }, []);

  async function onGenerate(event: FormEvent) {
    event.preventDefault();
    if (!cogniInstance || !datasetId) return;
    setError("");
    let mindmapContext: Record<string, unknown>;
    try {
      const parsed = JSON.parse(contextText);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("object");
      mindmapContext = parsed;
    } catch {
      setError(zh ? "脑图上下文需要是一份 JSON 对象。" : "Mind-map context must be a JSON object.");
      return;
    }
    setBusy(true);
    try {
      const next = await generateSopProposal(cogniInstance, {
        datasetId,
        roomKey,
        nodeUid,
        mindmapContext,
      });
      setProposal(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <details className="sop-load">
        <summary>{zh ? "载入节点并生成" : "Load a node and generate"}</summary>
        <form onSubmit={onGenerate}>
          <label>
            {zh ? "房间" : "Room"}
            <input value={roomKey} onChange={(event) => setRoomKey(event.target.value)} required />
          </label>
          <label>
            {zh ? "节点" : "Node"}
            <input value={nodeUid} onChange={(event) => setNodeUid(event.target.value)} required />
          </label>
          <label>
            {zh ? "脑图上下文" : "Mind-map context"}
            <textarea value={contextText} onChange={(event) => setContextText(event.target.value)} rows={6} required />
          </label>
          <button type="submit" disabled={busy || !datasetId}>{busy ? (zh ? "生成中" : "Generating") : (zh ? "生成 SOP 草案" : "Generate SOP draft")}</button>
          {error ? <p className="sop-error">{error}</p> : null}
        </form>
      </details>
      {proposal ? <SopViewer proposal={proposal} language={zh ? "zh" : "en"} /> : (
        <p className="sop-empty">
          {zh
            ? "还没有 SOP。在脑图中选中一个节点后，这里会显示人能读的流程、流程图、缺口和依据。"
            : "No SOP yet. After a mind-map node is selected, this page shows the procedure, flow, gaps, and rationale."}
        </p>
      )}
    </div>
  );
}
