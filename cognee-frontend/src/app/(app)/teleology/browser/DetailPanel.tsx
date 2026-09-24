"use client";

import { KIND_STRIPE, kindLabel, relLabel, shortId } from "./entityMeta";
import type { OntologyEdge, OntologyEntity } from "./types";

export default function DetailPanel({
  entity,
  edges,
  focusId,
  language,
  onSetFocus,
  onSelectNeighbor,
}: {
  entity: OntologyEntity | null;
  edges: OntologyEdge[];
  focusId: string | null;
  language: "zh" | "en";
  onSetFocus: (id: string) => void;
  onSelectNeighbor: (id: string) => void;
}) {
  const t = (en: string, zh: string) => (language === "zh" ? zh : en);

  if (!entity) {
    return (
      <aside className="onto-detail">
        <div className="onto-detail-empty">
          {t("Select a node to inspect properties and relations.", "选中节点以查看属性与关系。")}
        </div>
      </aside>
    );
  }

  const upstream = edges.filter((e) => e.targetId === entity.id);
  const downstream = edges.filter((e) => e.sourceId === entity.id);
  const stripe = KIND_STRIPE[entity.kind];

  return (
    <aside className="onto-detail">
      <div className="onto-detail-head">
        <span className="onto-detail-stripe" style={{ background: stripe }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="onto-detail-kind">{kindLabel(entity.kind, language)}</div>
          <div className="onto-detail-title">{entity.name}</div>
          <div className="onto-detail-uid" title={entity.id}>
            UID · {shortId(entity.id)}
          </div>
        </div>
      </div>

      <div className="onto-detail-actions">
        <button
          type="button"
          className="onto-btn onto-btn-primary"
          disabled={entity.id === focusId}
          onClick={() => onSetFocus(entity.id)}
        >
          {t("Set as center", "设为中心")}
        </button>
        <button
          type="button"
          className="onto-btn"
          onClick={() => onSelectNeighbor(entity.id)}
          title={t("Keep selected for path mode", "在路径模式中作为端点")}
        >
          {t("View path", "查看路径")}
        </button>
      </div>

      <section className="onto-detail-section">
        <h3>{t("Basics", "基本信息")}</h3>
        <dl className="onto-kv">
          <dt>{t("Type", "类型")}</dt>
          <dd>{kindLabel(entity.kind, language)}{entity.type && entity.type !== entity.kind ? ` · ${entity.type}` : ""}</dd>
          <dt>UID</dt>
          <dd className="onto-mono">{entity.id}</dd>
          {entity.status ? (
            <>
              <dt>{t("Status", "状态")}</dt>
              <dd>
                <span className="onto-status-dot" /> {entity.status}
              </dd>
            </>
          ) : null}
          {entity.parentName ? (
            <>
              <dt>{t("Parent", "上级")}</dt>
              <dd>{entity.parentName}</dd>
            </>
          ) : null}
        </dl>
      </section>

      {entity.description ? (
        <section className="onto-detail-section">
          <h3>{t("Description", "描述")}</h3>
          <p className="onto-detail-desc">{entity.description}</p>
        </section>
      ) : null}

      <section className="onto-detail-section">
        <h3>
          {t("Relations", "关联关系")}{" "}
          <span className="onto-muted">
            ↑{upstream.length} ↓{downstream.length}
          </span>
        </h3>
        {upstream.length === 0 && downstream.length === 0 ? (
          <div className="onto-muted" style={{ fontSize: 12 }}>
            {t("No edges in the current neighbourhood.", "当前邻域没有边。")}
          </div>
        ) : (
          <ul className="onto-rel-list">
            {upstream.map((e) => (
              <li key={e.id}>
                <button type="button" onClick={() => onSelectNeighbor(e.sourceId)}>
                  <span className="onto-rel-dir">↑</span>
                  <span className="onto-rel-name">{e.sourceName}</span>
                  <span className="onto-rel-pill">{relLabel(e.relationship, language)}</span>
                </button>
              </li>
            ))}
            {downstream.map((e) => (
              <li key={e.id}>
                <button type="button" onClick={() => onSelectNeighbor(e.targetId)}>
                  <span className="onto-rel-dir">↓</span>
                  <span className="onto-rel-name">{e.targetName}</span>
                  <span className="onto-rel-pill">{relLabel(e.relationship, language)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}
