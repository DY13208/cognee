import type { EntityKind } from "./types";

/** Quiet type stripe — not large fills. */
export const KIND_STRIPE: Record<EntityKind, string> = {
  Goal: "#7C8CFF",
  Project: "#A78BFA",
  Metric: "#34D399",
  Department: "#60A5FA",
  Person: "#FBBF24",
  Document: "#94A3B8",
  Entity: "#64748B",
  Other: "#52525B",
};

export const REL_PILL: Record<string, string> = {
  serves: "#60A5FA",
  advances: "#34D399",
  blocks: "#F87171",
  has_subgoal: "#A78BFA",
  depends_on: "#FBBF24",
  contributes: "#2DD4BF",
};

/** UI labels — keep API keys in English, show Chinese when language=zh. */
export const KIND_LABEL_ZH: Record<EntityKind, string> = {
  Goal: "目标",
  Project: "项目",
  Metric: "指标",
  Department: "部门",
  Person: "人员",
  Document: "文档",
  Entity: "实体",
  Other: "其他",
};

export const REL_LABEL_ZH: Record<string, string> = {
  serves: "服务于",
  advances: "推进",
  blocks: "阻碍",
  has_subgoal: "含子目标",
  has_detail_reference: "细节引用",
  depends_on: "依赖",
  contributes: "贡献于",
};

export function kindLabel(kind: string, language: "zh" | "en"): string {
  if (language !== "zh") return kind;
  return KIND_LABEL_ZH[kind as EntityKind] || kind;
}

export function relLabel(rel: string, language: "zh" | "en"): string {
  if (language !== "zh") return rel;
  return REL_LABEL_ZH[rel] || rel;
}

export function classifyKind(type: string, cpdKind?: string | null): EntityKind {
  const t = (type || "").toLowerCase();
  const c = (cpdKind || "").toLowerCase();
  if (c === "goal" || t === "goal" || t === "purpose" || t === "constraint") return "Goal";
  if (t.includes("project")) return "Project";
  if (t.includes("metric") || t.includes("kpi") || t.includes("indicator")) return "Metric";
  if (t.includes("department") || t.includes("org") || t.includes("team")) return "Department";
  if (t.includes("person") || t.includes("user") || t.includes("employee")) return "Person";
  if (t.includes("document") || t.includes("chunk") || t.includes("file")) return "Document";
  if (t === "entity") return "Entity";
  return "Other";
}

export function displayName(raw: string, fallback = ""): string {
  let s = String(raw || "");
  for (let i = 0; i < 3; i += 1) {
    const next = s
      .replace(/&amp;/gi, "&")
      .replace(/&lt;/gi, "<")
      .replace(/&gt;/gi, ">")
      .replace(/&quot;/gi, '"')
      .replace(/&#39;/gi, "'")
      .replace(/&nbsp;/gi, " ");
    if (next === s) break;
    s = next;
  }
  s = s.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
  return s || fallback || String(raw || "").trim();
}

export function shortId(id: string): string {
  if (!id) return "";
  return id.length > 12 ? `${id.slice(0, 8)}…` : id;
}
