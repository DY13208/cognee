"use client";

import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import { KIND_STRIPE, kindLabel } from "./entityMeta";
import { CARD_H, CARD_W } from "./layoutDag";
import type { LaidOutNode } from "./types";

const KIND_ICON: Record<string, string> = {
  Goal: "◎",
  Project: "▣",
  Metric: "▦",
  Department: "☰",
  Person: "☺",
  Document: "▤",
  Entity: "◇",
  Other: "○",
};

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
}) {
  const stripe = KIND_STRIPE[node.kind] || KIND_STRIPE.Other;
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
    background: isFocus ? "#1b2140" : "#151a2d",
    border: isFocus
      ? "1px solid #8478ff"
      : selected
        ? "1px solid #8478ff"
        : "1px solid rgba(112,130,199,0.34)",
    boxShadow: isFocus
      ? "0 0 0 3px rgba(117,104,255,0.16), 0 0 22px rgba(108,93,255,0.24), 0 10px 28px rgba(0,0,0,0.35)"
      : selected
        ? "0 0 0 3px rgba(117,104,255,0.13), 0 0 18px rgba(108,93,255,0.18)"
      : dragging
        ? "0 14px 32px rgba(0,0,0,0.5)"
        : "0 6px 18px rgba(0,0,0,0.28)",
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
          {KIND_ICON[node.kind] || "○"}
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
          {kindLabel(node.kind, language)}
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
      </div>
    </div>
  );
}
