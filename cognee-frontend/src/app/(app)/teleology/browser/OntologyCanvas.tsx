"use client";

import {
  useMemo,
  useRef,
  useState,
  useEffect,
  useCallback,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from "react";
import EntityCard from "./EntityCard";
import { REL_PILL, relLabel } from "./entityMeta";
import { layoutNeighborhood, CARD_W, CARD_H } from "./layoutDag";
import type { LaidOutEdge, LaidOutNode, OntologyEdge, OntologyEntity, ViewMode } from "./types";

type DragState = {
  id: string;
  pointerId: number;
  originX: number;
  originY: number;
  startClientX: number;
  startClientY: number;
};

type LayoutResult = {
  nodes: LaidOutNode[];
  edges: LaidOutEdge[];
  width: number;
  height: number;
};

export default function OntologyCanvas({
  focusId,
  entities,
  edges,
  selectedId,
  viewMode,
  hopDepth,
  relatedOnly,
  hiddenRels,
  hoverId,
  language,
  loading = false,
  onSelect,
  onSetFocus,
  onExpand,
  onCanvasClick,
  onHover,
  onViewMode,
  onRelatedOnly,
}: {
  focusId: string | null;
  entities: OntologyEntity[];
  edges: OntologyEdge[];
  selectedId: string | null;
  viewMode: ViewMode;
  hopDepth: number;
  relatedOnly: boolean;
  hiddenRels: Set<string>;
  hoverId: string | null;
  language: "zh" | "en";
  loading?: boolean;
  onSelect: (id: string | null) => void;
  onSetFocus: (id: string) => void;
  onExpand: (id: string) => void;
  onCanvasClick: () => void;
  onHover: (id: string | null) => void;
  onViewMode?: (m: ViewMode) => void;
  onRelatedOnly?: (v: boolean) => void;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const sizeRef = useRef({ w: 900, h: 560 });
  const [size, setSize] = useState({ w: 900, h: 560 });
  const [offsets, setOffsets] = useState<Record<string, { x: number; y: number }>>({});
  const dragRef = useRef<DragState | null>(null);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const lastGoodLayout = useRef<LayoutResult | null>(null);

  // Reset manual positions when the focus neighbourhood changes.
  useEffect(() => {
    setOffsets({});
    dragRef.current = null;
    setDraggingId(null);
  }, [focusId, viewMode, hopDepth]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const apply = () => {
      const next = { w: el.clientWidth, h: el.clientHeight };
      const prev = sizeRef.current;
      // Ignore tiny jitter from scrollbar appearing/disappearing.
      if (Math.abs(next.w - prev.w) < 12 && Math.abs(next.h - prev.h) < 12) return;
      sizeRef.current = next;
      setSize(next);
    };
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    sizeRef.current = { w: el.clientWidth, h: el.clientHeight };
    setSize(sizeRef.current);
    return () => ro.disconnect();
  }, []);

  const filteredEdges = useMemo(
    () => edges.filter((e) => !hiddenRels.has(e.relationship)),
    [edges, hiddenRels],
  );

  const computed = useMemo(() => {
    if (!focusId) return null;
    return layoutNeighborhood({
      focusId,
      entities,
      edges: filteredEdges,
      viewMode,
      canvasWidth: size.w,
      hopDepth,
    });
  }, [focusId, entities, filteredEdges, viewMode, size.w, hopDepth]);

  // Keep previous neighbourhood painted while the next focus is loading,
  // so the canvas doesn't flash empty / toggle scrollbars.
  if (computed && computed.nodes.length > 0) {
    lastGoodLayout.current = computed;
  }
  const layout: LayoutResult | null =
    computed && computed.nodes.length > 0
      ? computed
      : loading && lastGoodLayout.current
        ? lastGoodLayout.current
        : computed;

  const nodesWithOffsets = useMemo(() => {
    if (!layout) return [];
    return layout.nodes.map((n) => {
      const o = offsets[n.id];
      if (!o) return n;
      return { ...n, x: o.x, y: o.y };
    });
  }, [layout, offsets]);

  const edgesWithOffsets = useMemo(() => {
    if (!layout) return [];
    const pos = new Map(nodesWithOffsets.map((n) => [n.id, n]));
    return layout.edges.map((e) => {
      const s = pos.get(e.sourceId);
      const t = pos.get(e.targetId);
      if (!s || !t) return e;
      return {
        ...e,
        x1: s.x + CARD_W,
        y1: s.y + CARD_H / 2,
        x2: t.x,
        y2: t.y + CARD_H / 2,
      };
    });
  }, [layout, nodesWithOffsets]);

  const relatedIds = useMemo(() => {
    if (!relatedOnly || !focusId || !layout) return null;
    const ids = new Set<string>([focusId]);
    for (const e of layout.edges) {
      ids.add(e.sourceId);
      ids.add(e.targetId);
    }
    return ids;
  }, [relatedOnly, focusId, layout]);

  const onPointerMove = useCallback((e: PointerEvent) => {
    const drag = dragRef.current;
    if (!drag || e.pointerId !== drag.pointerId) return;
    const dx = e.clientX - drag.startClientX;
    const dy = e.clientY - drag.startClientY;
    setOffsets((prev) => ({
      ...prev,
      [drag.id]: { x: drag.originX + dx, y: drag.originY + dy },
    }));
  }, []);

  const endDrag = useCallback((e: PointerEvent) => {
    const drag = dragRef.current;
    if (!drag || e.pointerId !== drag.pointerId) return;
    dragRef.current = null;
    setDraggingId(null);
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", endDrag);
    window.removeEventListener("pointercancel", endDrag);
  }, [onPointerMove]);

  const startDrag = useCallback(
    (id: string, node: LaidOutNode, e: ReactPointerEvent) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      const cur = offsets[id] || { x: node.x, y: node.y };
      dragRef.current = {
        id,
        pointerId: e.pointerId,
        originX: cur.x,
        originY: cur.y,
        startClientX: e.clientX,
        startClientY: e.clientY,
      };
      setDraggingId(id);
      onSelect(id);
      window.addEventListener("pointermove", onPointerMove);
      window.addEventListener("pointerup", endDrag);
      window.addEventListener("pointercancel", endDrag);
    },
    [offsets, onSelect, onPointerMove, endDrag],
  );

  useEffect(() => {
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", endDrag);
      window.removeEventListener("pointercancel", endDrag);
    };
  }, [onPointerMove, endDrag]);

  const emptyStyle: CSSProperties = {
    flex: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "column",
    gap: 10,
    color: "rgba(232,231,228,0.45)",
    fontSize: 13,
    padding: 32,
    textAlign: "center",
  };

  const bottomBar = (
    <div className="onto-bottom-bar">
      <div className="onto-bottom-modes">
        {(
          [
            ["relation", "Relationship", "关系图"],
            ["chain", "Business chain", "业务链"],
            ["hierarchy", "Hierarchy", "层级图"],
            ["path", "Path", "路径"],
          ] as const
        ).map(([id, en, zh]) => (
          <button
            key={id}
            type="button"
            className={viewMode === id ? "is-active" : ""}
            onClick={() => onViewMode?.(id)}
          >
            {language === "zh" ? zh : en}
          </button>
        ))}
      </div>
      {focusId ? (
        <label className="onto-check" style={{ margin: 0 }}>
          <input
            type="checkbox"
            checked={relatedOnly}
            onChange={(e) => onRelatedOnly?.(e.target.checked)}
          />
          {language === "zh" ? "仅显示相关节点" : "Related nodes only"}
        </label>
      ) : null}
    </div>
  );

  if (!focusId) {
    return (
      <div className="onto-canvas-shell">
        <div className="onto-canvas" ref={wrapRef} style={emptyStyle} onClick={onCanvasClick}>
          <div style={{ fontSize: 15, fontWeight: 650, color: "rgba(232,231,228,0.72)" }}>
            {language === "zh" ? "先搜索或选择一个实体" : "Search or pick an entity first"}
          </div>
          <div style={{ maxWidth: 360, lineHeight: 1.5 }}>
            {language === "zh"
              ? "不会加载整张图。以该实体为中心，只展示一层上下游；其余用 +N 按需展开。"
              : "The full graph is never loaded. Focus one entity, show one hop up/down, expand with +N."}
          </div>
        </div>
        {bottomBar}
      </div>
    );
  }

  if (!layout || layout.nodes.length === 0) {
    return (
      <div className="onto-canvas-shell">
        <div className="onto-canvas" ref={wrapRef} style={emptyStyle}>
          {loading ? null : language === "zh" ? "该实体暂无可见关系" : "No visible relations for this entity"}
        </div>
        {bottomBar}
      </div>
    );
  }

  const activeChain = new Set<string>();
  if (hoverId || selectedId) {
    const seed = hoverId || selectedId!;
    activeChain.add(seed);
    for (const e of edgesWithOffsets) {
      if (e.sourceId === seed || e.targetId === seed) {
        activeChain.add(e.sourceId);
        activeChain.add(e.targetId);
        activeChain.add(e.id);
      }
    }
  }

  const canvasH = Math.max(size.h, layout.height);
  const canvasW = Math.max(size.w, layout.width);

  return (
    <div className="onto-canvas-shell">
      <div
        className="onto-canvas"
        ref={wrapRef}
        onClick={onCanvasClick}
        style={{
          flex: 1,
          minHeight: 0,
          position: "relative",
          overflow: "auto",
          scrollbarGutter: "stable",
        }}
      >
        {loading ? (
          <div
            className="onto-canvas-busy"
            aria-live="polite"
            aria-label={language === "zh" ? "更新中" : "Updating"}
          />
        ) : null}
        <div
          style={{
            position: "relative",
            width: canvasW,
            height: canvasH,
            minWidth: "100%",
            minHeight: "100%",
            opacity: loading ? 0.88 : 1,
            transition: "opacity 160ms ease",
          }}
        >
          <svg
            width={canvasW}
            height={canvasH}
            style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
          >
            <defs>
              <marker id="onto-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="rgba(232,231,228,0.35)" />
              </marker>
              <marker id="onto-arrow-hi" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="rgba(232,231,228,0.75)" />
              </marker>
            </defs>
            {edgesWithOffsets.map((e) => {
              const hi =
                activeChain.size === 0 ||
                activeChain.has(e.id) ||
                (activeChain.has(e.sourceId) && activeChain.has(e.targetId));
              const muted = activeChain.size > 0 && !hi;
              const midX = (e.x1 + e.x2) / 2;
              const midY = (e.y1 + e.y2) / 2;
              const color = REL_PILL[e.relationship] || "rgba(232,231,228,0.45)";
              return (
                <g key={e.id} opacity={muted ? 0.15 : hi && activeChain.size ? 1 : 0.55}>
                  <path
                    d={
                      viewMode === "hierarchy"
                        ? `M ${e.x1} ${e.y1} C ${e.x1} ${e.y1 + 28}, ${e.x2} ${e.y2 - 28}, ${e.x2} ${e.y2}`
                        : `M ${e.x1} ${e.y1} C ${e.x1 + 40} ${e.y1}, ${e.x2 - 40} ${e.y2}, ${e.x2} ${e.y2}`
                    }
                    fill="none"
                    stroke={hi && activeChain.size ? "rgba(232,231,228,0.55)" : "rgba(232,231,228,0.22)"}
                    strokeWidth={hi && activeChain.size ? 1.5 : 1}
                    markerEnd={hi && activeChain.size ? "url(#onto-arrow-hi)" : "url(#onto-arrow)"}
                  />
                  <foreignObject x={midX - 36} y={midY - 9} width={72} height={18}>
                    <div
                      style={{
                        fontSize: 9,
                        fontWeight: 600,
                        letterSpacing: "0.02em",
                        textAlign: "center",
                        color: muted ? "rgba(232,231,228,0.2)" : color,
                        background: "rgba(14,14,16,0.85)",
                        border: "1px solid rgba(255,255,255,0.06)",
                        borderRadius: 999,
                        padding: "1px 6px",
                        lineHeight: "14px",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {relLabel(e.relationship, language)}
                    </div>
                  </foreignObject>
                </g>
              );
            })}
          </svg>

          {nodesWithOffsets.map((n) => {
            if (relatedIds && !relatedIds.has(n.id)) return null;
            const dimmed = activeChain.size > 0 && !activeChain.has(n.id);
            return (
              <div
                key={n.id}
                onMouseEnter={() => onHover(n.id)}
                onMouseLeave={() => onHover(null)}
              >
                <EntityCard
                  node={n}
                  selected={selectedId === n.id}
                  isFocus={n.id === focusId}
                  dimmed={dimmed}
                  language={language}
                  dragging={draggingId === n.id}
                  onSelect={() => onSelect(n.id)}
                  onFocus={() => onSetFocus(n.id)}
                  onExpand={n.hiddenDegree ? () => onExpand(n.id) : undefined}
                  onPointerDown={(e) => startDrag(n.id, n, e)}
                />
              </div>
            );
          })}

          {viewMode !== "hierarchy" ? (
            <div
              style={{
                position: "absolute",
                left: 48,
                top: 12,
                display: "flex",
                gap: CARD_W + 120,
                fontSize: 10,
                fontWeight: 650,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: "rgba(232,231,228,0.28)",
                pointerEvents: "none",
              }}
            >
              <span style={{ width: CARD_W }}>
                {language === "zh" ? "上游" : "Upstream"}
              </span>
              <span style={{ width: CARD_W }}>
                {language === "zh" ? "焦点" : "Focus"}
              </span>
              <span style={{ width: CARD_W }}>
                {language === "zh" ? "下游" : "Downstream"}
              </span>
            </div>
          ) : (
            <div
              style={{
                position: "absolute",
                left: 48,
                top: 12,
                fontSize: 10,
                fontWeight: 650,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: "rgba(232,231,228,0.28)",
                pointerEvents: "none",
              }}
            >
              {language === "zh" ? "CPD 层级 · 上→下" : "CPD hierarchy · top→down"}
            </div>
          )}

          <div className="onto-minimap" aria-hidden>
            {nodesWithOffsets.map((n) => (
              <span
                key={n.id}
                style={{
                  left: `${(n.x / Math.max(layout.width, 1)) * 100}%`,
                  top: `${(n.y / Math.max(layout.height, 1)) * 100}%`,
                  background: n.id === focusId ? "#7c8cff" : "rgba(232,231,228,0.35)",
                }}
              />
            ))}
          </div>
        </div>
      </div>

      {bottomBar}
    </div>
  );
}
