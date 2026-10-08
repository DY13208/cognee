"use client";

import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import { KIND_STRIPE, kindLabel } from "./entityMeta";
import NodeCard from "./NodeCard";
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
    opacity: dimmed ? 0.58 : 1,
    cursor: dragging ? "grabbing" : "grab",
    zIndex: dragging ? 8 : isFocus ? 3 : selected ? 2 : 1,
    userSelect: "none",
    touchAction: "none",
  };

  const meta = node.description ? node.description.slice(0, 48) : node.status || node.parentName || "";

  return <NodeCard name={node.name} color={stripe}
    icon={evidence ? <EvidenceIcon /> : (KIND_ICON[node.kind] || "○")}
    label={[node.displayType || (node.type === "Data" ? (language === "zh" ? "数据" : "Data") : node.kind === "Purpose" ? "WHY" : kindLabel(node.kind, language)), proposed ? (language === "zh" ? " · AI建议" : " · Proposal") : semantic ? (language === "zh" ? " · 已确认" : " · Confirmed") : ""].join("")}
    meta={meta} appearance={{ focus: isFocus, selected, dragging, proposed, semantic }} style={style}
    headerAction={((node.childCount && node.childCount > 0) || (node.hiddenDegree && node.hiddenDegree > 0)) &&
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
    counts={<>
        <span>{language === "zh" ? "关系" : "Links"} {relationshipCount}</span>
        <span>{language === "zh" ? "子目标" : "Children"} {node.childCount || 0}</span>
        {evidenceCount > 0 ? <span>{language === "zh" ? "证据" : "Evidence"} {evidenceCount}</span> : null}
    </>}
    interactiveProps={{ onPointerDown, onClick: e => { e.stopPropagation(); onSelect(); },
      onDoubleClick: e => { e.stopPropagation(); onFocus(); },
      onKeyDown: e => { if (e.key === "Enter") onFocus(); } }} />;
}
