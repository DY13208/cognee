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
      setError("Failed to load ontologies.");
      console.error("Failed to load ontologies:", err);
    } finally {
      setLoading(false);
    }
  }, [cogniInstance]);

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
      notifications.show({ title: "Ontology deleted", message: `"${deleteTarget}" has been removed.`, color: "green", autoClose: 4000 });
    } catch (err) {
      notifications.show({ title: "Delete failed", message: err instanceof Error ? err.message : String(err), color: "red" });
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
      notifications.show({ title: "Ontology uploaded", message: `"${key}" is ready to use.`, color: "green", autoClose: 4000 });
      router.push(`/ontologies/${encodeURIComponent(key)}`);
    } catch (err) {
      notifications.show({ title: "Upload failed", message: err instanceof Error ? err.message : String(err), color: "red" });
      throw err;
    }
  }

  const ontologyList = Object.entries(ontologies);

  if (loading || isInitializing) {
    return (
      <>
        <TrackPageView page="Ontologies" />
        <PageLoading name="Ontologies" />
      </>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}>
      <TrackPageView page="Ontologies" />

      {/* Header */}
      <div style={{ padding: "24px 32px 16px", display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexShrink: 0 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <h1 style={{ fontSize: 20, fontWeight: 300, color: "#EDECEA", margin: 0, fontFamily: '"TWKLausanne", sans-serif' }}>Ontologies</h1>
          <p style={{ fontSize: 14, color: "rgba(237,236,234,0.55)", margin: 0 }}>Define domain vocabulary to structure how Cognee extracts entities and relationships.</p>
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
            Upload OWL
          </button>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="hover:bg-white/10 cursor-pointer"
            style={{ background: "rgba(255,255,255,0.06)", color: "rgba(237,236,234,0.7)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "8px 12px", fontSize: 13, fontWeight: 500, display: "flex", alignItems: "center", gap: 4 }}
            title="Refresh"
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
            <span style={{ fontSize: 16, fontWeight: 700, color: "#F87171" }}>Couldn&rsquo;t load ontologies</span>
            <p style={{ fontSize: 14, color: "rgba(237,236,234,0.35)", margin: 0, maxWidth: 340, textAlign: "center" }}>
              We couldn&rsquo;t reach the server. Please try again.
            </p>
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="cursor-pointer hover:bg-white/10"
              style={{ background: "rgba(255,255,255,0.06)", color: "#EDECEA", border: "1px solid rgba(255,255,255,0.15)", borderRadius: 8, padding: "8px 20px", fontSize: 14, fontWeight: 500, marginTop: 8 }}
            >
              {refreshing ? "Retrying…" : "Retry"}
            </button>
          </div>
        </div>
      ) : ontologyList.length > 0 ? (
        <div style={{ flex: 1, minHeight: 0, display: "flex", overflow: "hidden", marginInline: 32, marginBottom: 32, border: "1px solid rgba(255,255,255,0.12)", borderRadius: 12, background: "rgba(0,0,0,0.82)", backdropFilter: "blur(20px)" }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
            {/* Table header */}
            <div style={{ height: 44, padding: "0 20px", borderBottom: "1px solid rgba(255,255,255,0.1)", flexShrink: 0, display: "flex", alignItems: "center", gap: 16 }}>
              <span style={{ flex: 2, fontSize: 11, fontWeight: 700, color: "rgba(237,236,234,0.55)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Key</span>
              <span style={{ flex: 2, fontSize: 11, fontWeight: 700, color: "rgba(237,236,234,0.55)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Filename</span>
              <span style={{ flex: 1, fontSize: 11, fontWeight: 700, color: "rgba(237,236,234,0.55)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Size</span>
              <span style={{ flex: 1.5, fontSize: 11, fontWeight: 700, color: "rgba(237,236,234,0.55)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Uploaded</span>
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
                      title="Delete ontology"
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
            <span style={{ fontSize: 16, fontWeight: 700, color: "#EDECEA" }}>No ontologies yet</span>
            <p style={{ fontSize: 14, color: "rgba(237,236,234,0.35)", margin: 0, maxWidth: 400, textAlign: "center" }}>
              Ontologies define domain-specific vocabulary — the classes and relationships that exist in your domain. Upload an OWL file to guide how Cognee structures your knowledge graph.
            </p>
            <button
              onClick={() => setUploadOpen(true)}
              className="hover:bg-[#5A0ED6] cursor-pointer"
              style={{ background: "#6510F4", color: "#fff", border: "none", borderRadius: 8, padding: "8px 20px", fontSize: 14, fontWeight: 500, display: "flex", alignItems: "center", gap: 6, marginTop: 12 }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              Upload OWL
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
          title="Delete ontology"
          message={<>Are you sure you want to delete <strong>{deleteTarget}</strong>? This action cannot be undone.</>}
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
          busy={deleting}
        />
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
