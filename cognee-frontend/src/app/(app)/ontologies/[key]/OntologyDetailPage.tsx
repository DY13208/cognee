"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useCogniInstance } from "@/modules/tenant/TenantProvider";
import { TrackPageView } from "@/modules/analytics";
import { listOntologies, deleteOntology, uploadOntology, type OntologyMeta } from "@/modules/ontologies/ontologyApi";
import PageLoading from "@/ui/elements/PageLoading";
import DeleteConfirmModal from "@/ui/elements/DeleteConfirmModal";
import UploadOntologyModal from "../UploadOntologyModal";
import { notifications } from "@mantine/notifications";
import { formatDateTime } from "@/utils/formatDate";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

export default function OntologyDetailPage({ ontologyKey }: { ontologyKey: string }) {
  const router = useRouter();
  const { cogniInstance, isInitializing } = useCogniInstance();
  const [ontology, setOntology] = useState<OntologyMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showReplaceModal, setShowReplaceModal] = useState(false);

  const loadOntology = useCallback(async () => {
    if (!cogniInstance) return;
    try {
      const all = await listOntologies(cogniInstance);
      const found = all[ontologyKey];
      if (found) {
        setOntology(found);
        setNotFound(false);
      } else {
        setNotFound(true);
      }
    } catch (err) {
      console.error("Failed to load ontology:", err);
      setNotFound(true);
    } finally {
      setLoading(false);
    }
  }, [cogniInstance, ontologyKey]);

  useEffect(() => {
    if (!cogniInstance || isInitializing) return;
    loadOntology();
  }, [cogniInstance, isInitializing, loadOntology]);

  async function handleDelete() {
    if (!cogniInstance) return;
    setDeleting(true);
    try {
      await deleteOntology(cogniInstance, ontologyKey);
      notifications.show({ title: "Ontology deleted", message: `"${ontologyKey}" has been removed.`, color: "green", autoClose: 4000 });
      router.push("/ontologies");
    } catch (err) {
      notifications.show({ title: "Delete failed", message: err instanceof Error ? err.message : String(err), color: "red" });
      setDeleting(false);
    }
  }

  async function handleReplace(key: string, file: File, description?: string): Promise<void> {
    if (!cogniInstance) return;
    try {
      await deleteOntology(cogniInstance, ontologyKey);
      await uploadOntology(cogniInstance, key, file, description);
      setShowReplaceModal(false);
      notifications.show({ title: "Ontology replaced", message: `"${key}" has been uploaded.`, color: "green", autoClose: 4000 });
      if (key !== ontologyKey) {
        router.push(`/ontologies/${encodeURIComponent(key)}`);
      } else {
        await loadOntology();
      }
    } catch (err) {
      notifications.show({ title: "Replace failed", message: err instanceof Error ? err.message : String(err), color: "red" });
      throw err;
    }
  }

  if (loading || isInitializing) {
    return (
      <>
        <TrackPageView page="Ontology Detail" additionalProperties={{ ontology_key: ontologyKey }} />
        <PageLoading name="Ontology" />
      </>
    );
  }

  if (notFound) {
    return (
      <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}>
        <TrackPageView page="Ontology Detail" additionalProperties={{ ontology_key: ontologyKey }} />
        <div style={{ padding: "24px 32px 16px" }}>
          <Link href="/ontologies" style={{ fontSize: 13, color: "#BC9BFF", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
            Back to Ontologies
          </Link>
        </div>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", paddingInline: 32, paddingBottom: 32 }}>
          <div style={{ flex: 1, background: "rgba(255,255,255,0.06)", backdropFilter: "blur(12px)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16, padding: 48 }}>
            <span style={{ fontSize: 16, fontWeight: 700, color: "#EDECEA" }}>Ontology not found</span>
            <p style={{ fontSize: 14, color: "rgba(237,236,234,0.35)", margin: 0, maxWidth: 340, textAlign: "center" }}>
              The ontology &ldquo;{ontologyKey}&rdquo; doesn&rsquo;t exist or has been deleted.
            </p>
            <Link
              href="/ontologies"
              className="hover:bg-[#5A0ED6] cursor-pointer"
              style={{ background: "#6510F4", color: "#fff", border: "none", borderRadius: 8, padding: "8px 20px", fontSize: 14, fontWeight: 500, marginTop: 8, textDecoration: "none" }}
            >
              View all ontologies
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}>
      <TrackPageView page="Ontology Detail" additionalProperties={{ ontology_key: ontologyKey }} />

      {/* Breadcrumb */}
      <div style={{ padding: "24px 32px 0" }}>
        <Link href="/ontologies" style={{ fontSize: 13, color: "#BC9BFF", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
          Back to Ontologies
        </Link>
      </div>

      {/* Header */}
      <div style={{ padding: "16px 32px", display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexShrink: 0 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "#EDECEA", margin: 0 }}>{ontologyKey}</h1>
          {ontology?.description && (
            <p style={{ fontSize: 14, color: "rgba(237,236,234,0.55)", margin: 0 }}>{ontology.description}</p>
          )}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={() => setShowReplaceModal(true)}
            className="cursor-pointer hover:bg-white/10"
            style={{ background: "rgba(255,255,255,0.06)", color: "rgba(237,236,234,0.7)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 500, display: "flex", alignItems: "center", gap: 6 }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            Replace
          </button>
          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="cursor-pointer hover:bg-red-500/10"
            style={{ background: "rgba(255,255,255,0.06)", color: "#EF4444", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 500, display: "flex", alignItems: "center", gap: 6 }}
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="M3 4h10M6 4V3h4v1M5 4v8.5a.5.5 0 00.5.5h5a.5.5 0 00.5-.5V4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Delete
          </button>
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: "auto", padding: "0 32px 32px" }}>
        <div style={{ background: "rgba(0,0,0,0.82)", backdropFilter: "blur(20px)", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 12, padding: 24 }}>
          {/* Metadata grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 24 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "rgba(237,236,234,0.45)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Filename</span>
              <span style={{ fontSize: 14, color: "#EDECEA" }}>{ontology?.filename ?? "—"}</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "rgba(237,236,234,0.45)", letterSpacing: "0.08em", textTransform: "uppercase" }}>File Size</span>
              <span style={{ fontSize: 14, color: "#EDECEA" }}>{ontology ? formatBytes(ontology.size_bytes) : "—"}</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "rgba(237,236,234,0.45)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Uploaded</span>
              <span style={{ fontSize: 14, color: "#EDECEA" }}>{formatDateTime(ontology?.uploaded_at ?? null)}</span>
            </div>
            {ontology?.description && (
              <div style={{ display: "flex", flexDirection: "column", gap: 4, gridColumn: "1 / -1" }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "rgba(237,236,234,0.45)", letterSpacing: "0.08em", textTransform: "uppercase" }}>Description</span>
                <span style={{ fontSize: 14, color: "#EDECEA" }}>{ontology.description}</span>
              </div>
            )}
          </div>

          {/* Structure preview placeholder */}
          <div style={{ marginTop: 32, borderTop: "1px solid rgba(255,255,255,0.08)", paddingTop: 24 }}>
            <h3 style={{ fontSize: 14, fontWeight: 700, color: "#EDECEA", margin: "0 0 12px" }}>Structure Preview</h3>
            <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 24, display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="rgba(237,236,234,0.35)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 16v-4" />
                <path d="M12 8h.01" />
              </svg>
              <span style={{ fontSize: 13, color: "rgba(237,236,234,0.45)", textAlign: "center" }}>
                Structure preview coming in a later phase
              </span>
              <span style={{ fontSize: 12, color: "rgba(237,236,234,0.25)", textAlign: "center", maxWidth: 400 }}>
                Once available, this section will display the classes and relationships defined in your ontology.
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Delete confirmation modal */}
      {showDeleteConfirm && (
        <DeleteConfirmModal
          title="Delete ontology"
          message={<>Are you sure you want to delete <strong>{ontologyKey}</strong>? This action cannot be undone.</>}
          onConfirm={handleDelete}
          onCancel={() => setShowDeleteConfirm(false)}
          busy={deleting}
        />
      )}

      {/* Replace modal */}
      {showReplaceModal && (
        <UploadOntologyModal
          onClose={() => setShowReplaceModal(false)}
          onSubmit={handleReplace}
        />
      )}
    </div>
  );
}
