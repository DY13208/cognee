import type { CSSProperties } from "react";

export const EDGE_STROKE_WIDTH = 1.25;
export const EDGE_HIGHLIGHT_WIDTH = 1.6;
export const EDGE_LABEL_STYLE: CSSProperties = { fontSize: 9, fontWeight: 600, letterSpacing: "0.02em", textAlign: "center", background: "rgba(14,14,16,0.85)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 999, padding: "1px 6px", lineHeight: "14px", whiteSpace: "nowrap" };
/** Original hierarchy cubic curve, shared with network links. */
export function connectionPath(x1: number, y1: number, x2: number, y2: number, vertical = false) {
  return vertical ? `M ${x1} ${y1} C ${x1} ${y1 + 28}, ${x2} ${y2 - 28}, ${x2} ${y2}` : `M ${x1} ${y1} C ${x1 + 40} ${y1}, ${x2 - 40} ${y2}, ${x2} ${y2}`;
}
