import type { CSSProperties, ReactNode } from "react";
import { CARD_W } from "./layoutDag";

/** Shared card appearance for hierarchy and business network; layout stays view-specific. */
export function cardSurfaceStyle({ focus = false, selected = false, dragging = false, proposed = false, semantic = false }: {
  focus?: boolean; selected?: boolean; dragging?: boolean; proposed?: boolean; semantic?: boolean;
} = {}): CSSProperties {
  return {
    width: CARD_W, boxSizing: "border-box", display: "flex", flexDirection: "column", gap: 6,
    padding: "11px 12px 14px 14px", borderRadius: 10,
    background: focus ? "#1a1a1a" : "#101010",
    border: proposed ? "1px dashed #9181d9" : focus ? "1px solid rgba(232,231,228,0.72)" : semantic ? "1px solid #63a8db" : selected ? "1px solid rgba(232,231,228,0.55)" : "1px solid rgba(255,255,255,0.12)",
    boxShadow: focus ? "0 0 0 1px rgba(255,255,255,0.16), 0 10px 24px rgba(0,0,0,0.45)" : selected ? "0 0 0 1px rgba(255,255,255,0.1), 0 8px 20px rgba(0,0,0,0.4)" : dragging ? "0 14px 32px rgba(0,0,0,0.55)" : "0 6px 16px rgba(0,0,0,0.35)",
    color: "#E8E7E4", fontFamily: "inherit",
    transition: dragging ? "none" : "border-color 160ms ease, box-shadow 160ms ease, opacity 160ms ease",
  };
}
export const CARD_TITLE_STYLE: CSSProperties = { fontSize: 13, fontWeight: 700, lineHeight: 1.25, overflowWrap: "anywhere", textAlign: "left" };
export const CARD_META_STYLE: CSSProperties = { fontSize: 10, color: "rgba(232,231,245,0.68)", lineHeight: 1.4 };
export function typeBadgeStyle(color: string): CSSProperties {
  return { fontSize: 9, fontWeight: 700, letterSpacing: "0.04em", color, border: `1px solid ${color}55`, background: `${color}18`, borderRadius: 999, padding: "1px 7px", alignSelf: "flex-start" };
}
export function CardHeading({ name, color, icon, children, truncate = false }: { name: string; color: string; icon: ReactNode; children?: ReactNode; truncate?: boolean }) {
  return <div style={{ display: "flex", alignItems: "flex-start", gap: 8, width: "100%" }}>
    <span aria-hidden style={{ width: 22, height: 22, borderRadius: 6, display: "grid", placeItems: "center", fontSize: 11, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)", color, flexShrink: 0 }}>{icon}</span>
    <strong title={name} style={{ ...CARD_TITLE_STYLE, flex: 1, minWidth: 0, ...(truncate ? { overflow: "hidden", textOverflow: "ellipsis", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" } as CSSProperties : {}) }}>{name}</strong>
    {children}
  </div>;
}
