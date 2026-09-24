"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useCogniInstance } from "@/modules/tenant/TenantProvider";
import { TrackPageView } from "@/modules/analytics";
import { listOntologies, deleteOntology, uploadOntology, type OntologyMeta } from "@/modules/ontologies/ontologyApi";
import PageLoading from "@/ui/elements/PageLoading";
import DeleteConfirmModal from "@/ui/elements/DeleteConfirmModal";
import UploadOntologyModal from "./UploadOntologyModal";
import { notifications } from "@mantine/notifications";
import { formatDate } from "@/utils/formatDate";
import { t, useBusinessLanguage } from "@/modules/business/BusinessLanguageContext";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

function OntologyIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#BC9BFF" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
      <path d="M8 7h8" />
      <path d="M8 11h6" />
      <path d="M8 15h4" />
    </svg>
  );
}

export default function OntologiesPage() {
  const router = useRouter();
  const { language } = useBusinessLanguage();
  const { cogniInstance, isInitializing } = useCogniInstance();
  const [ontologies, setOntologies] = useState<Record<string, OntologyMeta>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const loadOntologies = useCallback(async () => {
    if (!cogniInstance) return;
    try {
      const data = await listOntologies(cogniInstance);
      setOntologies(data);
      setError(null);
    } catch (err) {
      setError(t(language, "Failed to load ontologies.", "加载本体失败。"));
      console.error("Failed to load ontologies:", err);
    } finally {
      setLoading(false);
    }
  }, [cogniInstance, language]);

  useEffect(() => {
    if (!cogniInstance || isInitializing) return;
    loadOntologies();
  }, [cogniInstance, isInitializing, loadOntologies]);

  async function handleRefresh() {
    setRefreshing(true);
    await loadOntologies();
    setRefreshing(false);
  }

  async function handleDelete() {
    if (!cogniInstance || !deleteTarget) return;
    setDeleting(true);
    try {
      await deleteOntology(cogniInstance, deleteTarget);
      setOntologies((prev) => {
        const next = { ...prev };
        delete next[deleteTarget];
        return next;
      });
      setDeleteTarget(null);
      notifications.show({
        title: t(language, "Ontology deleted", "本体已删除"),
        message: t(language, `"${deleteTarget}" has been removed.`, `「${deleteTarget}」已移除。`),
        color: "green",
        autoClose: 4000,
      });
    } catch (err) {
      notifications.show({
        title: t(language, "Delete failed", "删除失败"),
        message: err instanceof Error ? err.message : String(err),
        color: "red",
      });
    } finally {
      setDeleting(false);
    }
  }

  async function handleUpload(key: string, file: File, description?: string): Promise<void> {
    if (!cogniInstance) return;
    try {
      await uploadOntology(cogniInstance, key, file, description);
      const updated = await listOntologies(cogniInstance);
      setOntologies(updated);
      setUploadOpen(false);
      notifications.show({
        title: t(language, "Ontology uploaded", "本体已上传"),
        message: t(language, `"${key}" is ready to use.`, `「${key}」已可用。`),
        color: "green",
        autoClose: 4000,
      });
      router.push(`/ontologies/${encodeURIComponent(key)}`);
    } catch (err) {
      notifications.show({
        title: t(language, "Upload failed", "上传失败"),
        message: err instanceof Error ? err.message : String(err),
        color: "red",
      });
      throw err;
    }
  }

  const ontologyList = Object.entries(ontologies);

  if (loading || isInitializing) {
    return (
      <>
        <TrackPageView page="Ontologies" />
        <PageLoading name={t(language, "Ontologies", "本体")} />
      </>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}>
      <TrackPageView page="Ontologies" />

      {/* Header */}
      <div style={{ padding: "24px 32px 16px", display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexShrink: 0 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <h1 style={{ fontSize: 20, fontWeight: 300, color: "#EDECEA", margin: 0, fontFamily: '"TWKLausanne", sans-serif' }}>
            {t(language, "Ontologies", "本体")}
          </h1>
          <p style={{ fontSize: 14, color: "rgba(237,236,234,0.55)", margin: 0 }}>
            {t(
              language,
              "Define domain vocabulary to structure how Cognee extracts entities and relationships.",
              "定义领域词汇，引导 Cognee 如何抽取实体与关系。",
            )}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            onClick={() => setUploadOpen(true)}
            className="cursor-pointer"
            style={{ background: "#6510F4", color: "#fff", border: "none", borderRadius: 8, padding: "8px 14px", fontSize: 13, fontWeight: 500, display: "flex", alignItems: "center", gap: 6 }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            {t(language, "Upload OWL", "上传 OWL")}
          </button>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="hover:bg-white/10 cursor-pointer"
            style={{ background: "rgba(255,255,255,0.06)", color: "rgba(237,236,234,0.7)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "8px 12px", fontSize: 13, fontWeight: 500, display: "flex", alignItems: "center", gap: 4 }}
            title={t(language, "Refresh", "刷新")}
          >
            <svg
              width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="rgba(237,236,234,0.7)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
              style={refreshing ? { animation: "spin 1s linear infinite" } : undefined}
            >
              <path d="M21 2v6h-6" /><path d="M3 12a9 9 0 0115.36-6.36L21 8" /><path d="M3 22v-6h6" /><path d="M21 12a9 9 0 01-15.36 6.36L3 16" />
            </svg>
          </button>
        </div>
      </div>

      {/* Body */}
      {error ? (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", paddingInline: 32, paddingBottom: 32 }}>
          <div style={{ flex: 1, background: "rgba(255,255,255,0.06)", backdropFilter: "blur(12px)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 12, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, padding: 48 }}>
            <span style={{ fontSize: 16, fontWeight: 700, color: "#F87171" }}>
              {t(language, "Couldn't load ontologies", "无法加载本体")}
            </span>
            <p style={{ fontSize: 14, color: "rgba(237,236,234,0.35)", margin: 0, maxWidth: 340, textAlign: "center" }}>
              {t(language, "We couldn't reach the server. Please try again.", "无法连接服务器，请重试。")}
            </p>
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="cursor-pointer hover:bg-white/10"
              style={{ background: "rgba(255,255,255,0.06)", color: "#EDECEA", border: "1px solid rgba(255,255,255,0.15)", borderRadius: 8, padding: "8px 20px", fontSize: 14, fontWeight: 500, marginTop: 8 }}
            >
              {refreshing
                ? t(language, "Retrying…", "重试中…")
                : t(language, "Retry", "重试")}
            </button>
          </div>
        </div>
      ) : ontologyList.length > 0 ? (
        <div style={{ flex: 1, minHeight: 0, display: "flex", overflow: "hidden", marginInline: 32, marginBottom: 32, border: "1px solid rgba(255,255,255,0.12)", borderRadius: 12, background: "rgba(0,0,0,0.82)", backdropFilter: "blur(20px)" }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
            {/* Table header */}
            <div style={{ height: 44, padding: "0 20px", borderBottom: "1px solid rgba(255,255,255,0.1)", flexShrink: 0, display: "flex", alignItems: "center", gap: 16 }}>
              <span style={{ flex: 2, fontSize: 11, fontWeight: 700, color: "rgba(237,236,234,0.55)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                {t(language, "Key", "标识")}
              </span>
              <span style={{ flex: 2, fontSize: 11, fontWeight: 700, color: "rgba(237,236,234,0.55)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                {t(language, "Filename", "文件名")}
              </span>
              <span style={{ flex: 1, fontSize: 11, fontWeight: 700, color: "rgba(237,236,234,0.55)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                {t(language, "Size", "大小")}
              </span>
              <span style={{ flex: 1.5, fontSize: 11, fontWeight: 700, color: "rgba(237,236,234,0.55)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                {t(language, "Uploaded", "上传时间")}
              </span>
              <span style={{ width: 80 }} />
            </div>

            {/* Table body */}
            <div style={{ flex: 1, overflowY: "auto" }}>
              {ontologyList.map(([key, meta], i) => (
                <div
                  key={key}
                  onClick={() => router.push(`/ontologies/${encodeURIComponent(key)}`)}
                  className="cursor-pointer"
                  style={{
                    display: "flex", alignItems: "center", gap: 16,
                    padding: "12px 20px",
                    borderBottom: i < ontologyList.length - 1 ? "1px solid rgba(255,255,255,0.07)" : "none",
                    transition: "background 150ms",
                  }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.04)"; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}
                >
                  <span style={{ flex: 2, fontSize: 13, fontWeight: 500, color: "#EDECEA", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={key}>
                    {key}
                  </span>
                  <span style={{ flex: 2, fontSize: 13, color: "rgba(237,236,234,0.7)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={meta.filename}>
                    {meta.filename}
                  </span>
                  <span style={{ flex: 1, fontSize: 13, color: "rgba(237,236,234,0.55)" }}>
                    {formatBytes(meta.size_bytes)}
                  </span>
                  <span style={{ flex: 1.5, fontSize: 13, color: "rgba(237,236,234,0.55)" }}>
                    {formatDate(meta.uploaded_at)}
                  </span>
                  <div style={{ width: 80, display: "flex", justifyContent: "flex-end", gap: 4 }}>
                    <button
                      onClick={(e) => { e.stopPropagation(); setDeleteTarget(key); }}
                      className="cursor-pointer hover:bg-red-500/10"
                      style={{ background: "transparent", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 6, padding: 6, display: "flex", alignItems: "center", justifyContent: "center" }}
                      title={t(language, "Delete ontology", "删除本体")}
                    >
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                        <path d="M3 4h10M6 4V3h4v1M5 4v8.5a.5.5 0 00.5.5h5a.5.5 0 00.5-.5V4" stroke="#EF4444" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        /* Empty state */
        <div style={{ flex: 1, display: "flex", flexDirection: "column", paddingInline: 32, paddingBottom: 32 }}>
          <div style={{ flex: 1, background: "rgba(255,255,255,0.06)", backdropFilter: "blur(12px)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16, padding: 48 }}>
            <div style={{ width: 56, height: 56, background: "rgba(188,155,255,0.20)", border: "1px solid rgba(188,155,255,0.35)", borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <OntologyIcon />
            </div>
            <span style={{ fontSize: 16, fontWeight: 700, color: "#EDECEA" }}>
              {t(language, "No ontologies yet", "还没有本体")}
            </span>
            <p style={{ fontSize: 14, color: "rgba(237,236,234,0.35)", margin: 0, maxWidth: 400, textAlign: "center" }}>
              {t(
                language,
                "Ontologies define domain-specific vocabulary — the classes and relationships that exist in your domain. Upload an OWL file to guide how Cognee structures your knowledge graph.",
                "本体定义领域专用词汇——你领域中的类别与关系。上传 OWL 文件，可引导 Cognee 如何构建知识图谱。",
              )}
            </p>
            <button
              onClick={() => setUploadOpen(true)}
              className="hover:bg-[#5A0ED6] cursor-pointer"
              style={{ background: "#6510F4", color: "#fff", border: "none", borderRadius: 8, padding: "8px 20px", fontSize: 14, fontWeight: 500, display: "flex", alignItems: "center", gap: 6, marginTop: 12 }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              {t(language, "Upload OWL", "上传 OWL")}
            </button>
          </div>
        </div>
      )}

      {/* Upload modal */}
      {uploadOpen && (
        <UploadOntologyModal
          onClose={() => setUploadOpen(false)}
          onSubmit={handleUpload}
        />
      )}

      {/* Delete confirmation modal */}
      {deleteTarget && (
        <DeleteConfirmModal
          title={t(language, "Delete ontology", "删除本体")}
          message={
            language === "zh" ? (
              <>确定要删除 <strong>{deleteTarget}</strong> 吗？此操作不可撤销。</>
            ) : (
              <>Are you sure you want to delete <strong>{deleteTarget}</strong>? This action cannot be undone.</>
            )
          }
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
          busy={deleting}
        />
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
