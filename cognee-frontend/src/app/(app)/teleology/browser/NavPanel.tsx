"use client";

import type { EntityKind, ViewMode } from "./types";
import { KIND_STRIPE, kindLabel, relLabel } from "./entityMeta";

const ALL_KINDS: EntityKind[] = [
  "Goal",
  "Project",
  "Metric",
  "Department",
  "Person",
  "Document",
  "Entity",
  "Other",
];

const REL_OPTIONS = ["serves", "advances", "blocks", "has_subgoal"];

export default function NavPanel({
  language,
  viewMode,
  onViewMode,
  hopDepth,
  onHopDepth,
  relatedOnly,
  onRelatedOnly,
  hiddenRels,
  onToggleRel,
  kindFilter,
  onToggleKind,
  browseHits,
  onPickBrowse,
  browseLoading,
  pathStart,
  pathEnd,
  onClearPath,
}: {
  language: "zh" | "en";
  viewMode: ViewMode;
  onViewMode: (m: ViewMode) => void;
  hopDepth: number;
  onHopDepth: (n: number) => void;
  relatedOnly: boolean;
  onRelatedOnly: (v: boolean) => void;
  hiddenRels: Set<string>;
  onToggleRel: (rel: string) => void;
  kindFilter: Set<EntityKind>;
  onToggleKind: (k: EntityKind) => void;
  browseHits: { id: string; name: string; kind: string }[];
  onPickBrowse: (id: string) => void;
  browseLoading: boolean;
  pathStart: string | null;
  pathEnd: string | null;
  onClearPath: () => void;
}) {
  const t = (en: string, zh: string) => (language === "zh" ? zh : en);
  const modes: { id: ViewMode; en: string; zh: string }[] = [
    { id: "relation", en: "Relation", zh: "关系图" },
    { id: "chain", en: "Business chain", zh: "业务链" },
    { id: "hierarchy", en: "Hierarchy", zh: "层级图" },
    { id: "path", en: "Path", zh: "路径" },
  ];

  return (
    <aside className="onto-nav">
      <div className="onto-nav-block">
        <div className="onto-nav-label">{t("View", "视图")}</div>
        <div className="onto-mode-grid">
          {modes.map((m) => (
            <button
              key={m.id}
              type="button"
              className={`onto-mode-btn${viewMode === m.id ? " is-active" : ""}`}
              onClick={() => onViewMode(m.id)}
            >
              {language === "zh" ? m.zh : m.en}
            </button>
          ))}
        </div>
      </div>

      {viewMode === "path" ? (
        <div className="onto-nav-block">
          <div className="onto-nav-label">{t("Path endpoints", "路径端点")}</div>
          <div className="onto-muted" style={{ fontSize: 12, lineHeight: 1.45 }}>
            {t(
              "Select start, then end on the canvas (or from search). Only the connecting path stays visible.",
              "在画布或搜索中依次点选起点与终点，仅保留两实体间路径。",
            )}
          </div>
          <div style={{ marginTop: 8, fontSize: 11, color: "rgba(232,231,228,0.5)" }}>
            {t("Start", "起点")}: {pathStart ? short(pathStart) : "—"}
            <br />
            {t("End", "终点")}: {pathEnd ? short(pathEnd) : "—"}
          </div>
          {(pathStart || pathEnd) && (
            <button type="button" className="onto-btn" style={{ marginTop: 8 }} onClick={onClearPath}>
              {t("Clear path", "清除路径")}
            </button>
          )}
        </div>
      ) : null}

      <div className="onto-nav-block">
        <div className="onto-nav-label">{t("Filters", "过滤")}</div>
        <label className="onto-check">
          <input
            type="checkbox"
            checked={relatedOnly}
            onChange={(e) => onRelatedOnly(e.target.checked)}
          />
          {t("Related nodes only", "仅显示相关节点")}
        </label>
        <div className="onto-nav-sub">{t("Hop depth", "上下游层级")}</div>
        <div className="onto-seg">
          {[1, 2, 3].map((n) => (
            <button
              key={n}
              type="button"
              className={hopDepth === n ? "is-active" : ""}
              onClick={() => onHopDepth(n)}
            >
              {n}
            </button>
          ))}
        </div>
        <div className="onto-nav-sub">{t("Hide relations", "隐藏关系类型")}</div>
        {REL_OPTIONS.map((rel) => (
          <label key={rel} className="onto-check">
            <input
              type="checkbox"
              checked={hiddenRels.has(rel)}
              onChange={() => onToggleRel(rel)}
            />
            {relLabel(rel, language)}
          </label>
        ))}
      </div>

      <div className="onto-nav-block">
        <div className="onto-nav-label">{t("Entity types", "对象类型")}</div>
        {ALL_KINDS.map((k) => (
          <label key={k} className="onto-check">
            <input
              type="checkbox"
              checked={kindFilter.has(k)}
              onChange={() => onToggleKind(k)}
            />
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: 2,
                background: KIND_STRIPE[k],
                display: "inline-block",
                marginRight: 6,
              }}
            />
            {kindLabel(k, language)}
          </label>
        ))}
      </div>

      <div className="onto-nav-block" style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        <div className="onto-nav-label">{t("Browse / hits", "浏览 / 命中")}</div>
        <div className="onto-browse-list">
          {browseLoading ? (
            <div className="onto-muted" style={{ fontSize: 12, padding: 8 }}>
              {t("Loading…", "加载中…")}
            </div>
          ) : browseHits.length === 0 ? (
            <div className="onto-muted" style={{ fontSize: 12, padding: 8 }}>
              {t("Type in the top search, or open roots.", "在顶部搜索，或加载顶层目标。")}
            </div>
          ) : (
            browseHits.map((h) => (
              <button key={h.id} type="button" className="onto-browse-item" onClick={() => onPickBrowse(h.id)}>
                <span className="onto-browse-kind">{kindLabel(h.kind, language)}</span>
                <span className="onto-browse-name">{h.name}</span>
              </button>
            ))
          )}
        </div>
      </div>
    </aside>
  );
}

function short(id: string) {
  return id.length > 10 ? `${id.slice(0, 8)}…` : id;
}
