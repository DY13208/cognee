"use client";

import { connectionPath, EDGE_STROKE_WIDTH, EDGE_HIGHLIGHT_WIDTH, EDGE_LABEL_STYLE } from "./edgeAppearance";


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
  origins: Record<string, { x: number; y: number }>;
  startClientX: number;
  startClientY: number;
  moved: boolean;
};

type MarqueeState = {
  pointerId: number;
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  moved: boolean;
};

type PanState = {
  pointerId: number;
  startClientX: number;
  startClientY: number;
  startX: number;
  startY: number;
};

type LayoutResult = {
  nodes: LaidOutNode[];
  edges: LaidOutEdge[];
  width: number;
  height: number;
};

function nodesInMarquee(nodes: LaidOutNode[], area: MarqueeState): Set<string> {
  const left = Math.min(area.startX, area.endX);
  const right = Math.max(area.startX, area.endX);
  const top = Math.min(area.startY, area.endY);
  const bottom = Math.max(area.startY, area.endY);
  return new Set(nodes.filter((node) =>
    node.x < right && node.x + CARD_W > left && node.y < bottom && node.y + CARD_H > top,
  ).map((node) => node.id));
}

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
  zoom = 1,
  onSelect,
  onSetFocus,
  onExpand,
  onCanvasClick,
  onHover,
  positions,
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
  zoom?: number;
  positions?: Record<string, { x: number; y: number }>;
  onSelect: (id: string | null) => void;
  onSetFocus: (id: string) => void;
  onExpand: (id: string) => void;
  onCanvasClick: () => void;
  onHover: (id: string | null) => void;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const sizeRef = useRef({ w: 900, h: 560 });
  const [size, setSize] = useState({ w: 900, h: 560 });
  const [offsets, setOffsets] = useState<Record<string, { x: number; y: number }>>({});
  const dragRef = useRef<DragState | null>(null);
  const panRef = useRef<PanState | null>(null);
  const marqueeRef = useRef<MarqueeState | null>(null);
  const pointerMoveRef = useRef<(e: PointerEvent) => void>(() => {});
  const pointerEndRef = useRef<(e: PointerEvent) => void>(() => {});
  const onWindowMove = useCallback((e: PointerEvent) => pointerMoveRef.current(e), []);
  const onWindowEnd = useCallback((e: PointerEvent) => pointerEndRef.current(e), []);
  const [marquee, setMarquee] = useState<MarqueeState | null>(null);
  const [selectedNodeIds, setSelectedNodeIds] = useState<Set<string>>(() => new Set());
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [panning, setPanning] = useState(false);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const lastGoodLayout = useRef<LayoutResult | null>(null);
  const didDragRef = useRef(false);

  // Reset manual positions when the focus neighbourhood changes.
  useEffect(() => {
    setOffsets({});
    setPanOffset({ x: 0, y: 0 });
    dragRef.current = null;
    marqueeRef.current = null;
    setMarquee(null);
    setSelectedNodeIds(new Set());
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
    const result = layoutNeighborhood({
      focusId,
      entities,
      edges: filteredEdges,
      viewMode,
      canvasWidth: size.w,
      hopDepth,
    });
    if (!positions) return result;
    const nodes: LaidOutNode[] = entities.map(node => ({ ...node, column: node.id === focusId ? "focus" : "upstream", ...positions[node.id] }));
    const laidEdges = filteredEdges.map(edge => ({ ...edge, x1: 0, y1: 0, x2: 0, y2: 0 }));
    return { ...result, nodes, edges: laidEdges, width: Math.max(size.w, ...nodes.map(node => node.x + CARD_W + 60)), height: Math.max(560, ...nodes.map(node => node.y + CARD_H + 60)) };
  }, [focusId, entities, filteredEdges, viewMode, size.w, hopDepth, positions]);

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
      if (viewMode === "hierarchy") {
        const rel = e.relationship.toLowerCase();
        let parent = s;
        let child = t;
        if (rel === "advances") {
          parent = t;
          child = s;
        }
        return {
          ...e,
          x1: parent.x + CARD_W / 2,
          y1: parent.y + CARD_H,
          x2: child.x + CARD_W / 2,
          y2: child.y,
        };
      }
      return {
        ...e,
        x1: s.x + CARD_W,
        y1: s.y + CARD_H / 2,
        x2: t.x,
        y2: t.y + CARD_H / 2,
      };
    });
  }, [layout, nodesWithOffsets, viewMode]);

  const relationCountById = useMemo(() => {
    const counts = new Map<string, number>();
    for (const edge of filteredEdges) {
      if (!positions && !["serves", "advances", "blocks"].includes(edge.relationship)) continue;
      counts.set(edge.sourceId, (counts.get(edge.sourceId) || 0) + 1);
      counts.set(edge.targetId, (counts.get(edge.targetId) || 0) + 1);
    }
    return counts;
  }, [filteredEdges, positions]);

  const evidenceCountById = useMemo(() => {
    const counts = new Map<string, number>();
    for (const edge of filteredEdges) {
      if (edge.relationship !== "evidence") continue;
      counts.set(edge.targetId, (counts.get(edge.targetId) || 0) + 1);
    }
    return counts;
  }, [filteredEdges]);

  const onPointerMove = useCallback((e: PointerEvent) => {
    const pan = panRef.current;
    if (pan && e.pointerId === pan.pointerId) {
      setPanOffset({ x: pan.startX + e.clientX - pan.startClientX, y: pan.startY + e.clientY - pan.startClientY });
      return;
    }
    const selection = marqueeRef.current;
    if (selection && e.pointerId === selection.pointerId) {
      const content = contentRef.current;
      if (!content) return;
      const rect = content.getBoundingClientRect();
      const endX = (e.clientX - rect.left) / zoom;
      const endY = (e.clientY - rect.top) / zoom;
      const moved = selection.moved || Math.hypot(endX - selection.startX, endY - selection.startY) >= 4;
      const next = { ...selection, endX, endY, moved };
      marqueeRef.current = next;
      if (moved) {
        didDragRef.current = true;
        setMarquee(next);
        setSelectedNodeIds(nodesInMarquee(nodesWithOffsets, next));
      }
      return;
    }
    const drag = dragRef.current;
    if (!drag || e.pointerId !== drag.pointerId) return;
    const dx = (e.clientX - drag.startClientX) / zoom;
    const dy = (e.clientY - drag.startClientY) / zoom;
    if (!drag.moved && dx * dx + dy * dy < 25) return;
    if (!drag.moved) {
      drag.moved = true;
      didDragRef.current = true;
      setDraggingId(drag.id);
    }
    setOffsets((prev) => {
      const next = { ...prev };
      for (const [id, origin] of Object.entries(drag.origins)) next[id] = { x: origin.x + dx, y: origin.y + dy };
      return next;
    });
  }, [nodesWithOffsets, zoom]);

  const endPointer = useCallback(
    (e: PointerEvent) => {
      const pan = panRef.current;
      if (pan && e.pointerId === pan.pointerId) {
        panRef.current = null;
        setPanning(false);
        window.removeEventListener("pointermove", onWindowMove);
        window.removeEventListener("pointerup", onWindowEnd);
        window.removeEventListener("pointercancel", onWindowEnd);
        return;
      }
      const selection = marqueeRef.current;
      if (selection && e.pointerId === selection.pointerId) {
        marqueeRef.current = null;
        setMarquee(null);
        window.removeEventListener("pointermove", onWindowMove);
        window.removeEventListener("pointerup", onWindowEnd);
        window.removeEventListener("pointercancel", onWindowEnd);
        if (selection.moved) {
          window.setTimeout(() => { didDragRef.current = false; }, 0);
        }
        return;
      }
      const drag = dragRef.current;
      if (!drag || e.pointerId !== drag.pointerId) return;
      const wasMove = drag.moved;
      dragRef.current = null;
      setDraggingId(null);
      window.removeEventListener("pointermove", onWindowMove);
      window.removeEventListener("pointerup", onWindowEnd);
      window.removeEventListener("pointercancel", onWindowEnd);
      // Allow click handler to see whether this was a drag
      if (wasMove) {
        window.setTimeout(() => {
          didDragRef.current = false;
        }, 0);
      }
    },
    [onWindowMove, onWindowEnd],
  );

  const startCanvasPointerDown = useCallback(
    (e: ReactPointerEvent) => {
      const el = wrapRef.current;
      if (!el) return;
      if (e.button === 2 || e.button === 1) {
        e.preventDefault();
        panRef.current = {
          pointerId: e.pointerId,
          startClientX: e.clientX,
          startClientY: e.clientY,
          startX: panOffset.x,
          startY: panOffset.y,
        };
        setPanning(true);
        window.addEventListener("pointermove", onWindowMove);
        window.addEventListener("pointerup", onWindowEnd);
        window.addEventListener("pointercancel", onWindowEnd);
        return;
      }
      if ((e.target as Element).closest(".onto-entity-card, button, input")) return;
      if (e.button === 0) {
        const content = contentRef.current;
        if (!content) return;
        e.preventDefault();
        const rect = content.getBoundingClientRect();
        const startX = (e.clientX - rect.left) / zoom;
        const startY = (e.clientY - rect.top) / zoom;
        didDragRef.current = false;
        marqueeRef.current = { pointerId: e.pointerId, startX, startY, endX: startX, endY: startY, moved: false };
        window.addEventListener("pointermove", onWindowMove);
        window.addEventListener("pointerup", onWindowEnd);
        window.addEventListener("pointercancel", onWindowEnd);
        return;
      }
    },
    [onWindowMove, onWindowEnd, panOffset, zoom],
  );

  const startDrag = useCallback(
    (id: string, node: LaidOutNode, e: ReactPointerEvent) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      const group = selectedNodeIds.has(id) && selectedNodeIds.size > 1;
      const ids = group ? [...selectedNodeIds] : [id];
      if (!group) setSelectedNodeIds(new Set([id]));
      const byId = new Map(nodesWithOffsets.map((n) => [n.id, n]));
      const origins: Record<string, { x: number; y: number }> = {};
      for (const nid of ids) {
        const placed = byId.get(nid);
        origins[nid] = offsets[nid] || {
          x: placed?.x ?? (nid === id ? node.x : 0),
          y: placed?.y ?? (nid === id ? node.y : 0),
        };
      }
      didDragRef.current = false;
      dragRef.current = {
        id,
        pointerId: e.pointerId,
        origins,
        startClientX: e.clientX,
        startClientY: e.clientY,
        moved: false,
      };
      onSelect(id);
      window.addEventListener("pointermove", onWindowMove);
      window.addEventListener("pointerup", onWindowEnd);
      window.addEventListener("pointercancel", onWindowEnd);
    },
    [offsets, onSelect, onWindowMove, onWindowEnd, selectedNodeIds, nodesWithOffsets],
  );

  pointerMoveRef.current = onPointerMove;
  pointerEndRef.current = endPointer;

  useEffect(() => {
    return () => {
      window.removeEventListener("pointermove", onWindowMove);
      window.removeEventListener("pointerup", onWindowEnd);
      window.removeEventListener("pointercancel", onWindowEnd);
    };
  }, [onWindowMove, onWindowEnd]);

  const relatedIds = useMemo(() => {
    if (!relatedOnly || !focusId || !layout) return null;
    const ids = new Set<string>([focusId]);
    for (const e of layout.edges) {
      ids.add(e.sourceId);
      ids.add(e.targetId);
    }
    return ids;
  }, [relatedOnly, focusId, layout]);

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
      </div>
    );
  }

  if (!layout || layout.nodes.length === 0) {
    return (
      <div className="onto-canvas-shell">
        <div className="onto-canvas" ref={wrapRef} style={emptyStyle}>
          {loading ? null : language === "zh" ? "该实体暂无可见关系" : "No visible relations for this entity"}
        </div>
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
        onClick={() => {
          if (didDragRef.current || panning) return;
          setSelectedNodeIds(new Set());
          onCanvasClick();
        }}
        onPointerDown={startCanvasPointerDown}
        onContextMenu={(e) => e.preventDefault()}
        style={{
          flex: 1,
          minHeight: 0,
          position: "relative",
          overflow: "auto",
          cursor: panning ? "grabbing" : marquee ? "crosshair" : "default",
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
          ref={contentRef}
          style={{
            position: "relative",
            width: canvasW,
            height: canvasH,
            minWidth: "100%",
            minHeight: "100%",
            zoom,
            transform: `translate(${panOffset.x}px, ${panOffset.y}px)`,
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
              const proposed = e.status === "proposed";
              return (
                <g key={e.id} opacity={muted ? 0.15 : hi && activeChain.size ? 1 : 0.55}>
                  <path
                    d={connectionPath(e.x1, e.y1, e.x2, e.y2, viewMode === "hierarchy")}
                    fill="none"
                    stroke={proposed ? "#b1a3f4" : color}
                    strokeWidth={proposed || (hi && activeChain.size) ? EDGE_HIGHLIGHT_WIDTH : EDGE_STROKE_WIDTH}
                    strokeDasharray={proposed ? "6 4" : undefined}
                    markerEnd={hi && activeChain.size ? "url(#onto-arrow-hi)" : "url(#onto-arrow)"}
                  />
                  <foreignObject x={midX - 36} y={midY - 9} width={72} height={18}>
                    <div
                      style={{
                        ...EDGE_LABEL_STYLE,
                        fontSize: 9,
                        fontWeight: 600,
                        letterSpacing: "0.02em",
                        textAlign: "center",
                        color: muted ? "rgba(232,231,228,0.2)" : proposed ? "#b1a3f4" : color,
                        background: "rgba(14,14,16,0.85)",
                        border: proposed ? "1px dashed #9181d9" : "1px solid rgba(255,255,255,0.06)",
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
            const dimmed = activeChain.size > 0 && !activeChain.has(n.id) && !selectedNodeIds.has(n.id);
            const childCount = n.childCount || 0;
            const canEnter = childCount > 0 && n.id !== focusId;
            const inSelection = selectedNodeIds.has(n.id);
            const movingGroup = draggingId !== null && selectedNodeIds.has(draggingId) && inSelection;
            return (
              <div
                key={n.id}
                onMouseEnter={() => onHover(n.id)}
                onMouseLeave={() => onHover(null)}
              >
                <EntityCard
                  node={{
                    ...n,
                    childCount,
                    hiddenDegree: n.hiddenDegree || (canEnter ? childCount : undefined),
                  }}
                  selected={selectedId === n.id || inSelection}
                  isFocus={n.id === focusId}
                  dimmed={dimmed}
                  language={language}
                  dragging={draggingId === n.id || movingGroup}
                  relationshipCount={relationCountById.get(n.id) || 0}
                  evidenceCount={evidenceCountById.get(n.id) || 0}
                  onSelect={() => {
                    if (didDragRef.current) return;
                    onSelect(n.id);
                  }}
                  onFocus={() => onSetFocus(n.id)}
                  onExpand={
                    canEnter || n.hiddenDegree
                      ? () => onExpand(n.id)
                      : undefined
                  }
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

          {marquee?.moved ? (
            <div
              className="onto-marquee"
              style={{
                left: Math.min(marquee.startX, marquee.endX),
                top: Math.min(marquee.startY, marquee.endY),
                width: Math.abs(marquee.endX - marquee.startX),
                height: Math.abs(marquee.endY - marquee.startY),
              }}
            />
          ) : null}

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
    </div>
  );
}
