"use client";

import { useState, useEffect, useCallback, useRef, type ReactNode } from "react";
import { useCogniInstance } from "@/modules/tenant/TenantProvider";
import { TrackPageView } from "@/modules/analytics";
import {
  getTeleology,
  createTeleologyNode,
  updateTeleologyNode,
  deleteTeleologyNode,
  uploadTeleology,
  loadSampleTeleology,
  clearTeleology,
  type TeleologyStatus,
  type TeleologyNode,
  type TeleologyNodeInput,
  type TeleologyNodeType,
} from "@/modules/teleology/teleologyApi";
import PageLoading from "@/ui/elements/PageLoading";
import DeleteConfirmModal from "@/ui/elements/DeleteConfirmModal";
import TeleologyNodeModal from "./TeleologyNodeModal";
import { notifications } from "@mantine/notifications";
import { t, useBusinessLanguage } from "@/modules/business/BusinessLanguageContext";

const STATUS_COLOR: Record<string, string> = {
  active: "#34D399",
  proposed: "#FBBF24",
  achieved: "#60A5FA",
  abandoned: "rgba(237,236,234,0.35)",
};

const STATUS_ZH: Record<string, string> = {
  proposed: "提议",
  active: "进行中",
  achieved: "已达成",
  abandoned: "已放弃",
};

function GoalIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#BC9BFF" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <circle cx="12" cy="12" r="6" />
      <circle cx="12" cy="12" r="2" />
    </svg>
  );
}

export default function TeleologyPage() {
  const { language } = useBusinessLanguage();
  const { cogniInstance, isInitializing } = useCogniInstance();
  const [status, setStatus] = useState<TeleologyStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<TeleologyNode | null>(null);
  const [editor, setEditor] = useState<{ mode: "create" | "edit"; node?: TeleologyNode; defaultType?: TeleologyNodeType } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    if (!cogniInstance) return;
    try {
      const data = await getTeleology(cogniInstance);
      setStatus(data);
      setError(null);
    } catch (err) {
      setError(t(language, "Failed to load teleology.", "加载目的论失败。"));
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [cogniInstance, language]);

  useEffect(() => {
    if (!cogniInstance || isInitializing) return;
    load();
  }, [cogniInstance, isInitializing, load]);

  async function handleSave(input: TeleologyNodeInput) {
    if (!cogniInstance || !editor) return;
    try {
      const data =
        editor.mode === "edit" && editor.node
          ? await updateTeleologyNode(cogniInstance, editor.node.id, input)
          : await createTeleologyNode(cogniInstance, input);
      setStatus(data);
      setEditor(null);
      notifications.show({
        title: t(language, "Saved", "已保存"),
        message: t(language, `"${input.name}" is active for cognify.`, `「${input.name}」已生效，将在 cognify 时标注。`),
        color: "green",
        autoClose: 4000,
      });
    } catch (err) {
      notifications.show({
        title: t(language, "Save failed", "保存失败"),
        message: err instanceof Error ? err.message : String(err),
        color: "red",
      });
      throw err;
    }
  }

  async function handleDelete() {
    if (!cogniInstance || !deleteTarget) return;
    setBusy(true);
    try {
      const data = await deleteTeleologyNode(
        cogniInstance,
        deleteTarget.id,
        deleteTarget.type as TeleologyNodeType,
      );
      setStatus(data);
      setDeleteTarget(null);
      notifications.show({
        title: t(language, "Deleted", "已删除"),
        message: t(language, `"${deleteTarget.name}" removed.`, `「${deleteTarget.name}」已删除。`),
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
      setBusy(false);
    }
  }

  async function handleUpload(file: File) {
    if (!cogniInstance) return;
    setBusy(true);
    try {
      const data = await uploadTeleology(cogniInstance, file);
      setStatus(data);
      notifications.show({
        title: t(language, "YAML imported", "YAML 已导入"),
        message: t(language, "Replaced current teleology configuration.", "已替换当前目的论配置。"),
        color: "green",
        autoClose: 4000,
      });
    } catch (err) {
      notifications.show({
        title: t(language, "Upload failed", "上传失败"),
        message: err instanceof Error ? err.message : String(err),
        color: "red",
      });
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleSample() {
    if (!cogniInstance) return;
    setBusy(true);
    try {
      const data = await loadSampleTeleology(cogniInstance);
      setStatus(data);
      notifications.show({
        title: t(language, "Sample loaded", "已加载示例"),
        message: t(language, "Sample goals are now active.", "示例目标已激活。"),
        color: "green",
        autoClose: 4000,
      });
    } catch (err) {
      notifications.show({
        title: t(language, "Failed", "失败"),
        message: err instanceof Error ? err.message : String(err),
        color: "red",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleClear() {
    if (!cogniInstance) return;
    setBusy(true);
    try {
      const data = await clearTeleology(cogniInstance);
      setStatus(data);
      setConfirmClear(false);
      notifications.show({
        title: t(language, "Teleology cleared", "目的论已清除"),
        message: t(language, "Goal annotations are disabled until you add goals again.", "重新添加目标前不会再做标注。"),
        color: "green",
        autoClose: 4000,
      });
    } catch (err) {
      notifications.show({
        title: t(language, "Clear failed", "清除失败"),
        message: err instanceof Error ? err.message : String(err),
        color: "red",
      });
    } finally {
      setBusy(false);
    }
  }

  if (loading || isInitializing) {
    return (
      <>
        <TrackPageView page="Teleology" />
        <PageLoading name={t(language, "Teleology", "目的论")} />
      </>
    );
  }

  const hasNodes =
    (status?.goals.length ?? 0) + (status?.purposes.length ?? 0) + (status?.constraints.length ?? 0) > 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}>
      <TrackPageView page="Teleology" />

      <div style={{ padding: "24px 32px 16px", display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexShrink: 0, gap: 12 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <h1 style={{ fontSize: 20, fontWeight: 300, color: "#EDECEA", margin: 0, fontFamily: '"TWKLausanne", sans-serif' }}>
            {t(language, "Teleology", "目的论")}
          </h1>
          <p style={{ fontSize: 14, color: "rgba(237,236,234,0.55)", margin: 0 }}>
            {t(
              language,
              "Add goals and constraints in the form — no YAML required. Ontology stays in Brain.",
              "用表单添加目标与约束，不必写 YAML。本体仍在脑库里管理。",
            )}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0, flexWrap: "wrap", justifyContent: "flex-end" }}>
          <input
            ref={fileRef}
            type="file"
            accept=".yaml,.yml"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleUpload(f);
            }}
          />
          <button
            onClick={() => setEditor({ mode: "create", defaultType: "goal" })}
            disabled={busy}
            className="cursor-pointer"
            style={{ background: "#6510F4", color: "#fff", border: "none", borderRadius: 8, padding: "8px 14px", fontSize: 13, fontWeight: 500, display: "flex", alignItems: "center", gap: 6 }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            {t(language, "New goal", "新建目标")}
          </button>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            className="cursor-pointer hover:bg-white/10"
            style={{ background: "rgba(255,255,255,0.06)", color: "rgba(237,236,234,0.7)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "8px 12px", fontSize: 13 }}
            title={t(language, "Import YAML", "导入 YAML")}
          >
            {t(language, "Import YAML", "导入 YAML")}
          </button>
          {hasNodes && (
            <button
              onClick={() => setConfirmClear(true)}
              disabled={busy}
              className="cursor-pointer hover:bg-red-500/10"
              style={{ background: "rgba(255,255,255,0.06)", color: "#EF4444", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "8px 12px", fontSize: 13 }}
            >
              {t(language, "Clear all", "全部清除")}
            </button>
          )}
        </div>
      </div>

      {error ? (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", paddingInline: 32, paddingBottom: 32 }}>
          <div style={{ flex: 1, background: "rgba(255,255,255,0.06)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 12, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, padding: 48 }}>
            <span style={{ fontSize: 16, fontWeight: 700, color: "#F87171" }}>{error}</span>
            <button onClick={() => { setLoading(true); void load(); }} className="cursor-pointer" style={{ background: "rgba(255,255,255,0.06)", color: "#EDECEA", border: "1px solid rgba(255,255,255,0.15)", borderRadius: 8, padding: "8px 20px", fontSize: 14, marginTop: 8 }}>
              {t(language, "Retry", "重试")}
            </button>
          </div>
        </div>
      ) : hasNodes && status ? (
        <div style={{ flex: 1, minHeight: 0, overflow: "auto", padding: "0 32px 32px", display: "flex", flexDirection: "column", gap: 16 }}>
          <Section
            title={t(language, "Goals", "目标")}
            count={status.goals.length}
            onAdd={() => setEditor({ mode: "create", defaultType: "goal" })}
            addLabel={t(language, "Add goal", "添加目标")}
          >
            <NodeTable
              emptyLabel={t(language, "No goals yet — click Add goal.", "暂无目标，点击添加。")}
              nodes={status.goals}
              language={language}
              onEdit={(node) => setEditor({ mode: "edit", node })}
              onDelete={setDeleteTarget}
            />
          </Section>
          <Section
            title={t(language, "Constraints", "约束")}
            count={status.constraints.length}
            onAdd={() => setEditor({ mode: "create", defaultType: "constraint" })}
            addLabel={t(language, "Add constraint", "添加约束")}
          >
            <NodeTable
              emptyLabel={t(language, "No constraints yet.", "暂无约束。")}
              nodes={status.constraints}
              language={language}
              onEdit={(node) => setEditor({ mode: "edit", node })}
              onDelete={setDeleteTarget}
            />
          </Section>
          {(status.purposes.length > 0) && (
            <Section
              title={t(language, "Purposes", "目的")}
              count={status.purposes.length}
              onAdd={() => setEditor({ mode: "create", defaultType: "purpose" })}
              addLabel={t(language, "Add purpose", "添加目的")}
            >
              <NodeTable
                emptyLabel=""
                nodes={status.purposes}
                language={language}
                onEdit={(node) => setEditor({ mode: "edit", node })}
                onDelete={setDeleteTarget}
              />
            </Section>
          )}
        </div>
      ) : (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", paddingInline: 32, paddingBottom: 32 }}>
          <div style={{ flex: 1, background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16, padding: 48 }}>
            <div style={{ width: 56, height: 56, background: "rgba(188,155,255,0.20)", border: "1px solid rgba(188,155,255,0.35)", borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <GoalIcon />
            </div>
            <span style={{ fontSize: 16, fontWeight: 700, color: "#EDECEA" }}>
              {t(language, "No goals yet", "还没有目标")}
            </span>
            <p style={{ fontSize: 14, color: "rgba(237,236,234,0.35)", margin: 0, maxWidth: 420, textAlign: "center" }}>
              {t(
                language,
                "Create a goal in the form, or load the sample to try it out.",
                "用表单新建一个目标，或加载示例先体验一下。",
              )}
            </p>
            <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap", justifyContent: "center" }}>
              <button
                onClick={() => setEditor({ mode: "create", defaultType: "goal" })}
                disabled={busy}
                className="hover:bg-[#5A0ED6] cursor-pointer"
                style={{ background: "#6510F4", color: "#fff", border: "none", borderRadius: 8, padding: "8px 20px", fontSize: 14, fontWeight: 500 }}
              >
                {t(language, "New goal", "新建目标")}
              </button>
              <button
                onClick={() => void handleSample()}
                disabled={busy}
                className="cursor-pointer hover:bg-white/10"
                style={{ background: "rgba(255,255,255,0.06)", color: "#EDECEA", border: "1px solid rgba(255,255,255,0.15)", borderRadius: 8, padding: "8px 20px", fontSize: 14, fontWeight: 500 }}
              >
                {t(language, "Load sample", "加载示例")}
              </button>
            </div>
          </div>
        </div>
      )}

      {editor && (
        <TeleologyNodeModal
          initial={editor.mode === "edit" ? editor.node : null}
          defaultType={editor.defaultType || "goal"}
          onClose={() => setEditor(null)}
          onSubmit={handleSave}
        />
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          title={t(language, "Delete item", "删除条目")}
          message={
            language === "zh"
              ? <>确定删除 <strong>{deleteTarget.name}</strong> 吗？</>
              : <>Delete <strong>{deleteTarget.name}</strong>?</>
          }
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
          busy={busy}
        />
      )}

      {confirmClear && (
        <DeleteConfirmModal
          title={t(language, "Clear teleology", "清除目的论")}
          message={
            language === "zh"
              ? <>确定清除全部目标与约束吗？之后 cognify 将不再做目标标注。</>
              : <>Clear all goals and constraints? Cognify will stop annotating until you add goals again.</>
          }
          onConfirm={handleClear}
          onCancel={() => setConfirmClear(false)}
          busy={busy}
        />
      )}
    </div>
  );
}

function Section({
  title,
  count,
  children,
  onAdd,
  addLabel,
}: {
  title: string;
  count: number;
  children: ReactNode;
  onAdd?: () => void;
  addLabel?: string;
}) {
  return (
    <div style={{ border: "1px solid rgba(255,255,255,0.12)", borderRadius: 12, background: "rgba(0,0,0,0.82)", overflow: "hidden" }}>
      <div style={{ padding: "12px 20px", borderBottom: "1px solid rgba(255,255,255,0.08)", display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: "#EDECEA" }}>{title}</span>
        <span style={{ fontSize: 12, color: "rgba(237,236,234,0.35)" }}>{count}</span>
        {onAdd && (
          <button
            onClick={onAdd}
            className="cursor-pointer hover:bg-white/10"
            style={{ marginLeft: "auto", background: "transparent", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 6, padding: "4px 10px", fontSize: 12, color: "#BC9BFF" }}
          >
            + {addLabel}
          </button>
        )}
      </div>
      {children}
    </div>
  );
}

function NodeTable({
  emptyLabel,
  nodes,
  language,
  onEdit,
  onDelete,
}: {
  emptyLabel: string;
  nodes: TeleologyNode[];
  language: "zh" | "en";
  onEdit: (node: TeleologyNode) => void;
  onDelete: (node: TeleologyNode) => void;
}) {
  if (nodes.length === 0) {
    return (
      <div style={{ padding: "20px 24px", color: "rgba(237,236,234,0.35)", fontSize: 13 }}>
        {emptyLabel}
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {nodes.map((node, i) => (
        <div
          key={node.id}
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 16,
            padding: "14px 20px",
            borderBottom: i < nodes.length - 1 ? "1px solid rgba(255,255,255,0.06)" : "none",
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span style={{ fontSize: 14, fontWeight: 600, color: "#EDECEA" }}>{node.name}</span>
              <span style={{ fontSize: 11, fontWeight: 600, color: STATUS_COLOR[node.status] || "rgba(237,236,234,0.55)" }}>
                {language === "zh" ? (STATUS_ZH[node.status] || node.status) : node.status}
              </span>
            </div>
            {node.description && (
              <div style={{ fontSize: 13, color: "rgba(237,236,234,0.55)", marginTop: 4, lineHeight: 1.45 }}>
                {node.description}
              </div>
            )}
            {node.keywords?.length > 0 && (
              <div style={{ fontSize: 11, color: "rgba(237,236,234,0.3)", marginTop: 6 }}>
                {node.keywords.join(" · ")}
              </div>
            )}
          </div>
          <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
            <button
              onClick={() => onEdit(node)}
              className="cursor-pointer hover:bg-white/10"
              style={{ background: "transparent", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 6, padding: "6px 10px", fontSize: 12, color: "rgba(237,236,234,0.7)" }}
            >
              {t(language, "Edit", "编辑")}
            </button>
            <button
              onClick={() => onDelete(node)}
              className="cursor-pointer hover:bg-red-500/10"
              style={{ background: "transparent", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 6, padding: "6px 10px", fontSize: 12, color: "#EF4444" }}
            >
              {t(language, "Delete", "删除")}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
