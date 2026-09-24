"use client";

import { useState, type ReactElement } from "react";
import { Loader } from "@mantine/core";
import ModalShell from "@/ui/elements/ModalShell";
import { t, useBusinessLanguage } from "@/modules/business/BusinessLanguageContext";
import type {
  TeleologyNode,
  TeleologyNodeInput,
  TeleologyNodeStatus,
  TeleologyNodeType,
} from "@/modules/teleology/teleologyApi";

const STATUSES: TeleologyNodeStatus[] = ["proposed", "active", "achieved", "abandoned"];

const STATUS_ZH: Record<TeleologyNodeStatus, string> = {
  proposed: "提议",
  active: "进行中",
  achieved: "已达成",
  abandoned: "已放弃",
};

const TYPE_ZH: Record<TeleologyNodeType, string> = {
  goal: "目标",
  purpose: "目的",
  constraint: "约束",
};

const inputStyle = {
  background: "rgba(255,255,255,0.06)",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 8,
  padding: "8px 12px",
  fontSize: 14,
  fontFamily: "inherit",
  color: "#EDECEA",
  outline: "none",
  width: "100%",
} as const;

const labelStyle = {
  fontSize: 12,
  fontWeight: 700,
  color: "rgba(237,236,234,0.55)",
  textTransform: "uppercase" as const,
  letterSpacing: 0.3,
};

export default function TeleologyNodeModal({
  initial,
  defaultType = "goal",
  onSubmit,
  onClose,
}: {
  initial?: TeleologyNode | null;
  defaultType?: TeleologyNodeType;
  onSubmit: (input: TeleologyNodeInput) => Promise<void>;
  onClose: () => void;
}): ReactElement {
  const { language } = useBusinessLanguage();
  const editing = Boolean(initial);
  const [type, setType] = useState<TeleologyNodeType>(
    (initial?.type as TeleologyNodeType) || defaultType,
  );
  const [name, setName] = useState(initial?.name ?? "");
  const [status, setStatus] = useState<TeleologyNodeStatus>(
    (initial?.status as TeleologyNodeStatus) || "active",
  );
  const [description, setDescription] = useState(initial?.description ?? "");
  const [keywordsText, setKeywordsText] = useState((initial?.keywords ?? []).join(", "));
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setSubmitting(true);
    try {
      await onSubmit({
        type,
        name: trimmed,
        status,
        description: description.trim(),
        keywords: keywordsText
          .split(/[,，]/)
          .map((k) => k.trim())
          .filter(Boolean),
      });
    } catch {
      setSubmitting(false);
    }
  };

  return (
    <ModalShell
      width={460}
      onClose={() => { if (!submitting) onClose(); }}
      label={editing
        ? t(language, "Edit teleology item", "编辑目的论条目")
        : t(language, "New teleology item", "新建目的论条目")}
    >
      <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 12 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: "#EDECEA", margin: 0 }}>
          {editing
            ? t(language, "Edit", "编辑")
            : t(language, "New", "新建")}{" "}
          {language === "zh" ? TYPE_ZH[type] : type}
        </h2>
        <p style={{ fontSize: 13, color: "rgba(237,236,234,0.55)", margin: 0, lineHeight: "20px" }}>
          {t(
            language,
            "Describe what knowledge should serve — saved as goals YAML under the hood.",
            "描述知识应当服务的目标；后台会自动写成 YAML。",
          )}
        </p>
        <form onSubmit={handleSubmit}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {!editing && (
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <label style={labelStyle}>{t(language, "Type", "类型")}</label>
                <select
                  value={type}
                  onChange={(e) => setType(e.target.value as TeleologyNodeType)}
                  style={inputStyle}
                >
                  {(["goal", "constraint", "purpose"] as TeleologyNodeType[]).map((k) => (
                    <option key={k} value={k} style={{ background: "#1a1a1a" }}>
                      {language === "zh" ? TYPE_ZH[k] : k}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={labelStyle}>{t(language, "Name", "名称")}</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                placeholder={t(language, "e.g. Improve retrieval quality", "例如：提升检索质量")}
                style={inputStyle}
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={labelStyle}>{t(language, "Status", "状态")}</label>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as TeleologyNodeStatus)}
                style={inputStyle}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s} style={{ background: "#1a1a1a" }}>
                    {language === "zh" ? STATUS_ZH[s] : s}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={labelStyle}>{t(language, "Description", "描述")}</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                placeholder={t(language, "What is this for?", "这个目标是为了什么？")}
                style={{ ...inputStyle, resize: "vertical" }}
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label style={labelStyle}>
                {t(language, "Keywords", "关键词")}{" "}
                <span style={{ fontWeight: 400, textTransform: "none" }}>
                  ({t(language, "comma-separated", "逗号分隔")})
                </span>
              </label>
              <input
                value={keywordsText}
                onChange={(e) => setKeywordsText(e.target.value)}
                placeholder={t(language, "retrieval, search, relevance", "检索, 搜索, 相关性")}
                style={inputStyle}
              />
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="cursor-pointer"
              style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 500, color: "rgba(237,236,234,0.7)", fontFamily: "inherit" }}
            >
              {t(language, "Cancel", "取消")}
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="cursor-pointer"
              style={{ display: "flex", alignItems: "center", gap: 6, background: "#6510F4", border: "none", borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 500, color: "#fff", fontFamily: "inherit" }}
            >
              {submitting && <Loader size={14} color="#fff" />}
              {submitting
                ? t(language, "Saving...", "保存中...")
                : t(language, "Save", "保存")}
            </button>
          </div>
        </form>
      </div>
    </ModalShell>
  );
}
