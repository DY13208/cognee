"use client";

import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import { KIND_STRIPE, kindLabel } from "./entityMeta";
import { CARD_H, CARD_W } from "./layoutDag";
import type { LaidOutNode } from "./types";

const KIND_ICON: Record<string, string> = {
  Goal: "◎",
  Purpose: "✦",
  Constraint: "⊥",
  Project: "▣",
  Metric: "▦",
  Department: "☰",
  Person: "☺",
  Document: "▤",
  Entity: "◇",
  Other: "○",
};

function EvidenceIcon() {
  return <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <ellipse cx="12" cy="5" rx="8" ry="3" />
    <path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
    <path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
  </svg>;
}

export default function EntityCard({
  node,
  selected,
  isFocus,
  dimmed,
  dragging,
  onSelect,
  onFocus,
  onExpand,
  onPointerDown,
  language,
  relationshipCount,
  evidenceCount = 0,
}: {
  node: LaidOutNode;
  selected: boolean;
  isFocus: boolean;
  dimmed?: boolean;
  dragging?: boolean;
  onSelect: () => void;
  onFocus: () => void;
  onExpand?: () => void;
  onPointerDown?: (e: ReactPointerEvent) => void;
  language: "zh" | "en";
  relationshipCount: number;
  evidenceCount?: number;
}) {
  const evidence = node.type === "Data" || node.source === "company_tree";
  const stripe = evidence ? "#7eb6e8" : (KIND_STRIPE[node.kind] || KIND_STRIPE.Other);
  const proposed = node.reviewStatus === "proposed";
  const semantic = node.kind === "Purpose" || node.kind === "Constraint";
  const style: CSSProperties = {
    position: "absolute",
    left: node.x,
    top: node.y,
    width: CARD_W,
    height: CARD_H,
    boxSizing: "border-box",
    display: "flex",
    flexDirection: "column",
    gap: 6,
    padding: "11px 12px 10px 14px",
    borderRadius: 10,
    background: isFocus ? "#1a1a1a" : "#101010",
    border: proposed
      ? "1px dashed #9181d9"
      : isFocus
        ? "1px solid rgba(232,231,228,0.72)"
        : semantic
          ? "1px solid #63a8db"
          : selected
            ? "1px solid rgba(232,231,228,0.55)"
            : "1px solid rgba(255,255,255,0.12)",
    boxShadow: isFocus
      ? "0 0 0 1px rgba(255,255,255,0.16), 0 10px 24px rgba(0,0,0,0.45)"
      : selected
        ? "0 0 0 1px rgba(255,255,255,0.1), 0 8px 20px rgba(0,0,0,0.4)"
      : dragging
        ? "0 14px 32px rgba(0,0,0,0.55)"
        : "0 6px 16px rgba(0,0,0,0.35)",
    opacity: dimmed ? 0.58 : 1,
    cursor: dragging ? "grabbing" : "grab",
    color: "#E8E7E4",
    fontFamily: "inherit",
    transition: dragging
      ? "none"
      : "border-color 160ms ease, box-shadow 160ms ease, opacity 160ms ease",
    zIndex: dragging ? 8 : isFocus ? 3 : selected ? 2 : 1,
    userSelect: "none",
    touchAction: "none",
  };

  const meta = node.description ? node.description.slice(0, 48) : node.status || node.parentName || "";

  return (
    <div
      role="button"
      tabIndex={0}
      className="onto-entity-card"
      style={style}
      onPointerDown={onPointerDown}
      onClick={(e) => {
        e.stopPropagation();
        onSelect();
      }}
      onDoubleClick={(e) => {
        e.stopPropagation();
        onFocus();
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") onFocus();
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
        <span
          aria-hidden
          style={{
            width: 22,
            height: 22,
            borderRadius: 6,
            display: "grid",
            placeItems: "center",
            fontSize: 11,
            background: "rgba(255,255,255,0.05)",
            border: "1px solid rgba(255,255,255,0.08)",
            color: stripe,
            flexShrink: 0,
          }}
        >
          {evidence ? <EvidenceIcon /> : (KIND_ICON[node.kind] || "○")}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 700,
              lineHeight: 1.25,
              overflow: "hidden",
              textOverflow: "ellipsis",
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
            }}
            title={node.name}
          >
            {node.name}
          </div>
        </div>
        {((node.childCount && node.childCount > 0) || (node.hiddenDegree && node.hiddenDegree > 0)) &&
        onExpand ? (
          <button
            type="button"
            className="onto-expand-btn"
            title={
              language === "zh"
                ? node.childCount
                  ? "进入该节点的 CPD 子树"
                  : "展开更多关系"
                : node.childCount
                  ? "Enter this CPD subtree"
                  : "Expand relations"
            }
            onClick={(e) => {
              e.stopPropagation();
              onExpand();
            }}
          >
            {node.childCount && node.childCount > 0
              ? language === "zh"
                ? `进入 ${node.childCount}`
                : `Enter ${node.childCount}`
              : `+${node.hiddenDegree}`}
          </button>
        ) : null}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span
          style={{
            fontSize: 9,
            fontWeight: 700,
            letterSpacing: "0.04em",
            textTransform: "uppercase",
            color: stripe,
            border: `1px solid ${stripe}55`,
            background: `${stripe}18`,
            borderRadius: 999,
            padding: "1px 7px",
          }}
        >
          {node.type === "Data" ? (language === "zh" ? "数据" : "Data") : node.kind === "Purpose" ? "WHY" : kindLabel(node.kind, language)}
          {proposed ? (language === "zh" ? " · AI建议" : " · Proposal") : semantic ? (language === "zh" ? " · 已确认" : " · Confirmed") : ""}
        </span>
      </div>

      {meta ? (
        <div
          style={{
            fontSize: 10,
            color: "rgba(232,231,245,0.68)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {meta}
        </div>
      ) : null}
      <div className="onto-card-counts">
        <span>{language === "zh" ? "关系" : "Links"} {relationshipCount}</span>
        <span>{language === "zh" ? "子目标" : "Children"} {node.childCount || 0}</span>
        {evidenceCount > 0 ? <span>{language === "zh" ? "证据" : "Evidence"} {evidenceCount}</span> : null}
      </div>
    </div>
  );
}
