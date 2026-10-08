"use client";

import type { CSSProperties, HTMLAttributes, ReactNode } from "react";
import { CardHeading, cardSurfaceStyle, typeBadgeStyle, CARD_META_STYLE } from "./cardAppearance";
import { CARD_H } from "./layoutDag";

/** The complete node card, shared by hierarchy and operating network canvases. */
export default function NodeCard({ name, color, icon, label, meta, counts, headerAction, footer,
  appearance, style, className = "", interactiveProps, showDetails = true, metaClassName,
}: {
  name: string; color: string; icon: ReactNode; label: string; meta?: string;
  counts?: ReactNode; headerAction?: ReactNode; footer?: ReactNode;
  appearance?: Parameters<typeof cardSurfaceStyle>[0]; style?: CSSProperties; className?: string;
  interactiveProps: HTMLAttributes<HTMLDivElement>; showDetails?: boolean; metaClassName?: string;
}) {
  return <div className={`onto-entity-card ${className}`} data-component="node-card"
    style={{ ...cardSurfaceStyle(appearance), height: "auto", minHeight: CARD_H, overflow: "visible", ...style }}>
    <div {...interactiveProps} role="button" tabIndex={0}
      style={{ display: "flex", flex: 1, flexDirection: "column", gap: 6, cursor: "grab", userSelect: "none", touchAction: "none" }}>
      <CardHeading name={name} color={color} icon={icon} truncate>{headerAction}</CardHeading>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span data-node-type style={typeBadgeStyle(color)}>{label}</span>
      </div>
      {showDetails && meta && <div className={metaClassName} style={{ ...CARD_META_STYLE, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{meta}</div>}
      {showDetails && counts && <div className="onto-card-counts">{counts}</div>}
    </div>
    {footer && <div className="onto-card-footer" style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>{footer}</div>}
  </div>;
}
