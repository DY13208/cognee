"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { CogneeInstance } from "@/modules/instances/types";
import { getGoalModel, getGoalNetworkLoops, type GoalModelView, type GoalNetworkLoop } from "@/modules/teleology/teleologyApi";
import SideRail from "./SideRail";
import { businessName, CAUSAL_RELATIONS, currentNetwork, DEFAULT_TYPES, edgeKey, NETWORK_TYPES, NODE_COLORS, NODE_LABELS, networkType, RELATION_LABELS, sourceOf, targetOf, type NetworkType } from "./goalNetwork";
import "./goalNetwork.css";
import { businessGoals, businessNetwork, canvasProjection, clusteredLayout, connectionAvailability, defaultBusinessGoal, supportingNodes, SUPPORT_TYPES, type NetworkScope } from "./networkProjection";
import { CardHeading, cardSurfaceStyle, CARD_META_STYLE, typeBadgeStyle } from "./cardAppearance";
import { connectionPath, EDGE_STROKE_WIDTH, EDGE_HIGHLIGHT_WIDTH, EDGE_LABEL_STYLE } from "./edgeAppearance";
import { REL_PILL } from "./entityMeta";
import { NODE_ICONS } from "./goalNetwork";
import { CARD_W } from "./layoutDag";

function MeasuredNetworkCard({ id, lod, appearance, children, onMeasure }: {
  id: string; lod: string; appearance: Parameters<typeof cardSurfaceStyle>[0]; children: ReactNode;
  onMeasure: (id: string, lod: string, height: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => { if (element.offsetHeight > 0) onMeasure(id, lod, element.offsetHeight); };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [id, lod, onMeasure]);
  return <div ref={ref} className="onto-entity-card network-node-card" style={cardSurfaceStyle(appearance)}>{children}</div>;
}

export function GoalNetworkPresentation({ model, loops, loopError, loopView = false, onShowHierarchy }: {
  model: GoalModelView; loops: GoalNetworkLoop[]; loopError?: string; loopView?: boolean;
  onShowHierarchy?: () => void;
}) {
  const [types, setTypes] = useState<Set<NetworkType>>(() => new Set(DEFAULT_TYPES));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedLoopId, setSelectedLoopId] = useState<string | null>(null);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<NetworkScope>("business");
  const [contextScope, setContextScope] = useState<Exclude<NetworkScope, "focus">>("business");
  const [businessGoalId, setBusinessGoalId] = useState<string | null>(() => defaultBusinessGoal(model));
  const [focusId, setFocusId] = useState<string | null>(null);
  const [hops, setHops] = useState<1 | 2 | "all">(1);
  const [showSupport, setShowSupport] = useState(false);
  const supportAutoTypes = useRef(new Set<NetworkType>());
  const [expandedGoals, setExpandedGoals] = useState<Set<string>>(() => new Set());
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [nodeOffsets, setNodeOffsets] = useState<Record<string, { x: number; y: number }>>({});
  const [nodeHeights, setNodeHeights] = useState<Record<string, number>>({});
  const [layoutHeights, setLayoutHeights] = useState<Record<string, number>>({});
  const measureNode = useCallback((id: string, lod: string, height: number) => {
    const measured = Math.ceil(height);
    setNodeHeights(old => old[`${id}|${lod}`] === measured ? old : { ...old, [`${id}|${lod}`]: measured });
    // Reserve grown rows so zoom-level changes cannot cause fit/LOD oscillation.
    setLayoutHeights(old => (old[id] || 0) >= measured ? old : { ...old, [id]: measured });
  }, []);
  const graphRef = useRef<SVGGElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const [canvasSize, setCanvasSize] = useState({ width: 1000, height: 700 });
  const nodeDrag = useRef<{ id: string; pointerId: number; x: number; y: number; offsetX: number; offsetY: number; inverse: DOMMatrix } | null>(null);
  const nodeMoved = useRef(false);
  const drag = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);
  useEffect(() => {
    if (window.innerWidth < 1100) setLeftOpen(false);
    if (window.innerWidth < 900) setRightOpen(false);
  }, []);
  useEffect(() => {
    if (!canvasRef.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(entries => { const bounds = entries[0]?.contentRect; if (bounds?.width && bounds.height) setCanvasSize({ width: bounds.width, height: bounds.height }); });
    observer.observe(canvasRef.current);
    return () => observer.disconnect();
  }, []);
  const directory = useMemo(() => currentNetwork(model, false), [model]);
  const anchors = useMemo(() => businessGoals(model), [model]);
  const network = useMemo(() => contextScope === "global" ? directory : contextScope === "pilot" ? currentNetwork(model) : businessNetwork(model, businessGoalId), [model, directory, contextScope, businessGoalId]);
  const selectedLoop = loops.find(loop => loop.loop_id === selectedLoopId) || null;
  const loopNodes = useMemo(() => new Set(selectedLoop?.nodes || []), [selectedLoop]);
  const loopEdges = useMemo(() => new Set((selectedLoop?.edges || []).map(edgeKey)), [selectedLoop]);
  const projection = useMemo(() => canvasProjection(network, { types, showSupport, expandedGoals, focusId: scope === "focus" ? focusId : null, hops, loopNodes, loopEdges }), [network, types, showSupport, expandedGoals, scope, focusId, hops, loopNodes, loopEdges]);
  const visible = projection.nodes;
  const layout = useMemo(() => clusteredLayout(visible, projection.relations, layoutHeights), [visible, projection.relations, layoutHeights]);
  const basePositions = layout.positions;
  const positioned = basePositions.map(p => ({ ...p, x: p.x + (nodeOffsets[p.node.id]?.x || 0), y: p.y + (nodeOffsets[p.node.id]?.y || 0) }));
  const byId = new Map(positioned.map(position => [position.node.id, position]));
  const relations = projection.relations;
  const selected = directory.nodes.find(node => node.id === selectedId);
  const width = Math.max(920, ...layout.clusters.map(p => p.x + p.width + 20));
  const height = Math.max(600, ...layout.clusters.map(p => p.y + p.height + 20));
  const displayScale = zoom * Math.min(canvasSize.width / width, canvasSize.height / height);
  const lod = displayScale < .65 ? "far" : displayScale < 1.15 ? "medium" : "near";
  const minimumHeight = lod === "far" ? 56 : lod === "near" ? 120 : 80;
  const heightOf = (id: string) => nodeHeights[`${id}|${lod}`] || minimumHeight;
  const incident = selected ? network.relations.filter(edge => sourceOf(edge) === selected.id || targetOf(edge) === selected.id) : [];
  const availability = connectionAvailability(network, scope === "focus" ? focusId : null);
  const outsideScope = scope === "focus" && !availability.total && connectionAvailability(directory, focusId).total > 0;
  const nameOf = (id: string) => { const node = directory.nodes.find(n => n.id === id); return node ? businessName(node) : "未载入的节点"; };
  function pickNode(id: string) {
    setSelectedId(id); setRightOpen(true); setSelectedLoopId(null);
    if (!network.nodes.some(n => n.id === id)) {
      const owner = anchors.find(n => businessNetwork(model, n.id).nodes.some(member => member.id === id));
      if (owner) { setBusinessGoalId(owner.id); setContextScope("business"); } else setContextScope("global");
    }
    setFocusId(id); setScope("focus"); setHops(1); setZoom(1); setPan({ x: 0, y: 0 });
  }
  function changeScope(next: NetworkScope) {
    setScope(next); setSelectedLoopId(null); setExpandedGoals(new Set()); setZoom(1); setPan({ x: 0, y: 0 });
    if (next !== "focus") { setContextScope(next); setFocusId(null); setSelectedId(null); }
    else setFocusId(selectedId || businessGoalId);
  }
  function toggle(type: NetworkType) { supportAutoTypes.current.delete(type); setTypes(old => { const next = new Set(old); if (next.has(type)) next.delete(type); else next.add(type); return next; }); }
  function toggleSupport(checked: boolean) {
    setShowSupport(checked);
    if (checked) {
      supportAutoTypes.current = new Set(SUPPORT_TYPES.filter(type => !types.has(type)));
      setTypes(old => new Set([...old, ...SUPPORT_TYPES]));
    } else {
      const automatic = new Set(supportAutoTypes.current);
      setTypes(old => new Set([...old].filter(type => !automatic.has(type))));
      supportAutoTypes.current.clear();
    }
  }
  function revealConnections() {
    supportAutoTypes.current.clear();
    setTypes(old => new Set([...old, ...availability.nodeTypes]));
    if (availability.supporting) setShowSupport(true);
  }
  function focusLoop(loop: GoalNetworkLoop) {
    setSelectedLoopId(old => old === loop.loop_id ? null : loop.loop_id); setSelectedId(null); setFocusId(null); setScope(contextScope);
    if (loop.nodes.some(id => !network.nodes.some(n => n.id === id))) { setContextScope("global"); setScope("global"); }
    setZoom(1); setPan({ x: 0, y: 0 });
  }

  return <div className="onto-root goal-network-root">
    <div className="onto-body">
      <SideRail side="left" open={leftOpen} onOpen={() => setLeftOpen(true)} expandLabel="展开经营网络导航">
        <aside className="onto-nav network-nav">
          <div className="network-panel-header onto-detail-head"><strong>经营网络导航</strong><button className="onto-panel-close" onClick={() => setLeftOpen(false)} aria-label="收起经营网络导航">×</button></div>
          <p className="network-muted">完整目录 · {directory.nodes.length} 个节点</p>
          <select aria-label="网络展示范围" value={scope} onChange={e => changeScope(e.target.value as NetworkScope)} className="network-scope"><option value="global">公司全局</option><option value="business">当前业务 Goal</option><option value="pilot">当前 Network Pilot</option><option value="focus">当前选中节点 Focus</option></select>
          <select aria-label="当前业务 Goal" value={businessGoalId || ""} onChange={e => { setBusinessGoalId(e.target.value); setSelectedId(null); changeScope("business"); }} className="network-scope">{anchors.length ? anchors.map(node => <option key={node.id} value={node.id}>{businessName(node)}</option>) : <option value={businessGoalId || ""}>{businessGoalId ? nameOf(businessGoalId) : "暂无业务 Goal"}</option>}</select>
          <input className="onto-nav-search" aria-label="搜索业务节点" placeholder="搜索业务名称" value={query} onChange={e => setQuery(e.target.value)} />
          {NETWORK_TYPES.map(type => {
            const scopeIds = new Set(network.nodes.map(n => n.id));
            const nodes = directory.nodes.filter(node => networkType(node) === type).sort((a, b) => Number(scopeIds.has(b.id)) - Number(scopeIds.has(a.id)));
            return <details key={type} open={DEFAULT_TYPES.includes(type) ? true : undefined} className="network-nav-group">
              <summary><span className="onto-file-chevron" aria-hidden><svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M3.2 1.6L6.8 5L3.2 8.4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" /></svg></span><i style={{ background: NODE_COLORS[type] }} />{type === "goal" ? "经营目标" : NODE_LABELS[type]}<span className="onto-nav-count">{nodes.length}</span></summary>
              {nodes.filter(n => businessName(n).includes(query)).map(node => <div key={node.id} className={`onto-file-row network-nav-row${selectedId === node.id ? " is-selected" : ""}`}><button className="onto-file-name network-nav-node" onClick={() => pickNode(node.id)}>{businessName(node)}</button></div>)}
              {nodes.length === 0 && <p className="network-muted">暂无节点</p>}
            </details>;
          })}
        </aside>
      </SideRail>
      <main className="onto-canvas-shell network-main">
        <div className="network-controls"><div className="network-type-filters" role="group" aria-label="画布节点类型筛选">{NETWORK_TYPES.map(type => <button key={type} aria-pressed={types.has(type)} className={`onto-btn${types.has(type) ? " is-active" : ""}`} onClick={() => toggle(type)}><i style={{ background: NODE_COLORS[type] }} />{NODE_LABELS[type]}</button>)}</div><span className="network-muted">显示 {visible.length} / {network.nodes.length}</span></div>
        <div className="network-context-bar"><span>{contextScope === "business" ? `当前业务范围 · ${nameOf(businessGoalId || "")}` : contextScope === "pilot" ? "当前 Network Pilot" : "公司全局"} · {relations.length} 条可见关系</span><label><input type="checkbox" checked={showSupport} onChange={e => toggleSupport(e.target.checked)} />显示支撑关系</label>{scope === "focus" && <><strong>Focus · {nameOf(focusId || "")}</strong><div role="group" aria-label="Focus 跳数">{([1, 2, "all"] as const).map(hop => <button className="onto-btn" key={hop} aria-pressed={hops === hop} onClick={() => setHops(hop)}>{hop === "all" ? "全部" : `${hop}跳`}</button>)}</div><button className="onto-btn" onClick={() => changeScope(contextScope)}>退出 Focus</button></>}</div>
        {(loopView || selectedLoop || loops.length > 0) && <div className="network-loop-strip"><strong>反馈回路（{loopError ? "未载入" : loops.length}）</strong>{loops.map((loop, i) => <button className="onto-btn" key={loop.loop_id} aria-pressed={selectedLoopId === loop.loop_id} onClick={() => focusLoop(loop)}>Loop {String(i + 1).padStart(2, "0")} · {loop.loop_type === "Reinforcing" ? "增强回路" : "平衡回路"}</button>)}{!loopError && !loops.length && <span>服务端未返回反馈回路</span>}{selectedLoop && <button className="onto-btn" onClick={() => setSelectedLoopId(null)}>取消高亮</button>}</div>}
        {loopError && <p role="alert" className="network-error">反馈回路暂时无法载入：{loopError}</p>}
        <div ref={canvasRef} className={`network-canvas lod-${lod}`} data-lod={lod}>
          <svg aria-label="经营关系网络画布" viewBox={`0 0 ${width} ${height}`} onPointerDown={e => { if ((e.target as Element).closest(".network-node")) return; drag.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y }; e.currentTarget.setPointerCapture(e.pointerId); }} onPointerMove={e => { if (drag.current) { const bounds = e.currentTarget.getBoundingClientRect(); const ratio = Math.max(width / bounds.width, height / bounds.height); setPan({ x: drag.current.panX + (e.clientX - drag.current.x) * ratio, y: drag.current.panY + (e.clientY - drag.current.y) * ratio }); } }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
            <defs><marker id="network-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="rgba(232,231,228,0.35)" /></marker><marker id="network-arrow-hi" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="rgba(232,231,228,0.75)" /></marker></defs>
            <g ref={graphRef} transform={`translate(${pan.x + width * (1 - zoom) / 2},${pan.y + height * (1 - zoom) / 2}) scale(${zoom})`}>
              {layout.clusters.map(cluster => <g key={cluster.name} className="network-cluster" opacity={selectedLoop ? .08 : 1}><text x={cluster.x + 20} y={cluster.y + 12} style={{ fontSize: Math.min(30, Math.max(12, 12 / displayScale)) }}>{cluster.name}</text><path d={`M${cluster.x + 20},${cluster.y + 20}H${cluster.x + cluster.width - 20}`} /></g>)}
              {relations.map(edge => {
                const source = byId.get(sourceOf(edge))!; const target = byId.get(targetOf(edge))!;
                const sourceHeight = heightOf(source.node.id), targetHeight = heightOf(target.node.id);
                const dx = target.x - source.x, dy = target.y + targetHeight / 2 - source.y - sourceHeight / 2;
                const sourceBoundary = Math.max(Math.abs(dx) / CARD_W, Math.abs(dy) / sourceHeight) || 1;
                const targetBoundary = Math.max(Math.abs(dx) / CARD_W, Math.abs(dy) / targetHeight) || 1;
                const sx = source.x + CARD_W / 2 + dx / sourceBoundary / 2, sy = source.y + sourceHeight / 2 + dy / sourceBoundary / 2;
                const tx = target.x + CARD_W / 2 - dx / targetBoundary / 2, ty = target.y + targetHeight / 2 - dy / targetBoundary / 2;
                const causal = CAUSAL_RELATIONS.has(edge.relationship || "");
                const highlighted = loopEdges.has(edgeKey(edge));
                const dimmed = selectedLoop && !highlighted;
                const color = REL_PILL[edge.relationship || ""] || "rgba(232,231,228,0.45)";
                return <g key={edge.id || edgeKey(edge)} className={`network-edge${causal ? " is-causal" : " is-structural"}${highlighted ? " is-loop" : ""}`} opacity={dimmed ? .08 : highlighted ? 1 : causal ? .55 : .3} data-relationship={edge.relationship} data-loop-highlighted={highlighted}>
                  <title>{nameOf(sourceOf(edge))} · {RELATION_LABELS[edge.relationship || ""] || "其他关系"} · {nameOf(targetOf(edge))}{edge.reason ? `：${edge.reason}` : ""}</title>
                  <path d={connectionPath(sx, sy, tx, ty, Math.abs(dy) > Math.abs(dx))} style={{ stroke: color, strokeWidth: highlighted ? EDGE_HIGHLIGHT_WIDTH : EDGE_STROKE_WIDTH }} markerEnd={highlighted ? "url(#network-arrow-hi)" : "url(#network-arrow)"} />
                  {lod !== "far" && <foreignObject x={(sx + tx) / 2 - 36} y={(sy + ty) / 2 - 9} width="72" height="18" style={{ overflow: "visible", pointerEvents: "none" }}><div className="network-edge-label" style={{ ...EDGE_LABEL_STYLE, color }}>{RELATION_LABELS[edge.relationship || ""] || "其他关系"}</div></foreignObject>}
                </g>;
              })}
              {positioned.map(({ node, x, y }) => <foreignObject key={node.id} x={x} y={y} width={CARD_W} height={heightOf(node.id)} style={{ overflow: "visible" }} opacity={selectedLoop && !loopNodes.has(node.id) ? .08 : 1}>
                <MeasuredNetworkCard id={node.id} lod={lod} appearance={{ focus: loopNodes.has(node.id) || focusId === node.id, selected: selectedId === node.id, proposed: node.status === "proposed", semantic: networkType(node) === "constraint" }} onMeasure={measureNode}>
                <button className={`network-node${selectedId === node.id ? " is-selected" : ""}${loopNodes.has(node.id) ? " is-loop" : ""}`}
                  onPointerDown={e => {
                    if (e.button !== 0) return;
                    e.stopPropagation();
                    nodeMoved.current = false;
                    const matrix = graphRef.current?.getScreenCTM();
                    if (!matrix) return;
                    const inverse = matrix.inverse();
                    const point = new DOMPoint(e.clientX, e.clientY).matrixTransform(inverse);
                    const offset = nodeOffsets[node.id] || { x: 0, y: 0 };
                    nodeDrag.current = { id: node.id, pointerId: e.pointerId, x: point.x, y: point.y, offsetX: offset.x, offsetY: offset.y, inverse };
                    e.currentTarget.setPointerCapture?.(e.pointerId);
                  }}
                  onPointerMove={e => {
                    const active = nodeDrag.current;
                    if (!active || active.id !== node.id || active.pointerId !== e.pointerId) return;
                    e.stopPropagation();
                    const point = new DOMPoint(e.clientX, e.clientY).matrixTransform(active.inverse);
                    const dx = point.x - active.x, dy = point.y - active.y;
                    if (!nodeMoved.current && Math.hypot(dx, dy) < 4) return;
                    nodeMoved.current = true;
                    setNodeOffsets(old => ({ ...old, [node.id]: { x: active.offsetX + dx, y: active.offsetY + dy } }));
                  }}
                  onPointerUp={e => { e.stopPropagation(); nodeDrag.current = null; }}
                  onPointerCancel={() => { nodeDrag.current = null; }}
                  onLostPointerCapture={() => { nodeDrag.current = null; }}
                  onKeyDown={e => {
                    const delta: Record<string, [number, number]> = { ArrowLeft: [-20, 0], ArrowRight: [20, 0], ArrowUp: [0, -20], ArrowDown: [0, 20] };
                    if (!delta[e.key]) return;
                    e.preventDefault(); e.stopPropagation();
                    const [dx, dy] = delta[e.key];
                    setNodeOffsets(old => ({ ...old, [node.id]: { x: (old[node.id]?.x || 0) + dx, y: (old[node.id]?.y || 0) + dy } }));
                  }}
                  onClick={() => { if (nodeMoved.current) { nodeMoved.current = false; return; } pickNode(node.id); }} title="点击进入 Focus，拖动移动节点；方向键微调位置" aria-label={`${NODE_LABELS[networkType(node)]}：${businessName(node)}`}>
                    {lod === "far" ? <strong style={{ fontSize: Math.min(24, Math.max(13, 12 / displayScale)) }}>{businessName(node)}</strong> : <><CardHeading name={businessName(node)} color={NODE_COLORS[networkType(node)]} icon={NODE_ICONS[networkType(node)]} /><small style={typeBadgeStyle(NODE_COLORS[networkType(node)])}>{NODE_LABELS[networkType(node)]}</small></>}
                    {lod === "near" && <><span className="network-node-description" style={CARD_META_STYLE}>{node.description || node.reason || "暂无说明"}</span><span className="network-node-degree onto-card-counts">关系 {network.relations.filter(e => sourceOf(e) === node.id || targetOf(e) === node.id).length}</span></>}
                  </button>
                  {lod !== "far" && networkType(node) === "goal" && <div className="network-support-badges">{SUPPORT_TYPES.map(type => { const count = supportingNodes(node.id, network, type).length; return count ? <button className="onto-btn" key={type} aria-label={`${businessName(node)}展开附属${NODE_LABELS[type]}`} aria-pressed={expandedGoals.has(`${node.id}|${type}`)} onPointerDown={e => e.stopPropagation()} onClick={() => setExpandedGoals(old => { const next = new Set(old); const key = `${node.id}|${type}`; if (next.has(key)) next.delete(key); else next.add(key); return next; })}>{NODE_LABELS[type]} {count}</button> : null; })}</div>}
                </MeasuredNetworkCard>
              </foreignObject>)}
            </g>
          </svg>
          {!visible.length && <div className="teleology-canvas-empty network-empty" role="status">
            {availability.total ? <><strong>已有 {availability.total} 条关系，被当前筛选隐藏</strong><p>因果关系 {availability.causal} 条 · 支撑关系 {availability.supporting} 条。关系端点的节点类型也需要显示。</p><button className="onto-btn" onClick={revealConnections}>{scope === "focus" ? "显示该节点的关联关系" : "显示当前范围的关联关系"}</button></>
              : outsideScope ? <><strong>该节点的关系位于当前业务范围之外</strong><p>当前范围没有相连节点，可切换范围查看已有关系。</p><button className="onto-btn" onClick={() => changeScope("global")}>查看公司全局</button></>
              : <><strong>{scope === "focus" ? "该节点尚未建立经营影响关系" : "当前业务范围尚未建立经营影响关系"}</strong><p>目标层级与来源证据不会被用来填充经营网络。</p>{onShowHierarchy && <button className="onto-btn" onClick={onShowHierarchy}>查看目标层级</button>}</>}
          </div>}
          <div className="network-zoom"><button className="onto-btn" aria-label="缩小网络" onClick={() => setZoom(v => Math.max(.4, v - .15))}>−</button><span>{Math.round(zoom * 100)}%</span><button className="onto-btn" aria-label="放大网络" onClick={() => setZoom(v => Math.min(2.5, v + .15))}>＋</button><button className="onto-btn" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}>适应画布</button></div>
        </div>
        <footer className="network-legend"><span><i />因果关系</span><span><i className="is-structural" />非因果关系</span><span>拖动节点调整位置 · 拖动画布平移 · 点击节点查看详情</span></footer>
      </main>
      <SideRail side="right" open={rightOpen} onOpen={() => setRightOpen(true)} expandLabel="展开网络详情">
        <aside className="onto-detail network-detail">
          <div className="network-panel-header onto-detail-head"><strong>{selected ? "节点详情" : "网络概览"}</strong><button className="onto-panel-close" onClick={() => setRightOpen(false)} aria-label="收起网络详情">×</button></div>
          {selected ? <><span className="network-kind onto-detail-kind" style={{ color: NODE_COLORS[networkType(selected)] }}>{NODE_LABELS[networkType(selected)]}</span><h2 className="onto-detail-title">{businessName(selected)}</h2><p>{selected.description}</p><h3>理由</h3><p>{selected.reason || "暂无说明"}</p><p className="network-muted">置信度 {Math.round((selected.confidence || 0) * 100)}% · {(selected.evidence || []).length} 条证据</p><h3>关联关系（{incident.length}）</h3>{incident.map(edge => <div className="network-detail-edge" key={edge.id || edgeKey(edge)}><span>{nameOf(sourceOf(edge))} <b>{RELATION_LABELS[edge.relationship || ""] || "其他关系"} →</b> {nameOf(targetOf(edge))}</span>{edge.condition != null && <small>条件：{typeof edge.condition === "object" ? edge.condition.expression || "由服务端判定" : typeof edge.condition === "boolean" ? edge.condition ? "已满足" : "未满足" : edge.condition}</small>}</div>)}</> : <><h2>经营网络</h2><p className="network-muted">画布展示当前业务中的有效连接。完整节点目录保留在左侧，点击节点进入 1 跳 Focus。</p></>}
          <section className="network-isolated onto-detail-section"><h3>未参与当前网络（{projection.isolated.length}）</h3><p className="network-muted">未进入当前画布的节点，点击查看详情与已有关系。</p>{projection.isolated.map(node => <button className="onto-file-name" key={node.id} onClick={() => { setSelectedId(node.id); setRightOpen(true); }}>{NODE_LABELS[networkType(node)]} · {businessName(node)}<small>{connectionAvailability(network, node.id).total ? "已有关系，被当前筛选隐藏" : "尚未建立经营影响关系"}</small></button>)}</section>
          {selected && networkType(selected) === "goal" && <section><h3>附属信息</h3><div className="network-support-badges">{SUPPORT_TYPES.map(type => { const count = supportingNodes(selected.id, network, type).length; return count ? <button className="onto-btn" key={type} onClick={() => setExpandedGoals(old => { const next = new Set(old); const key = `${selected.id}|${type}`; if (next.has(key)) next.delete(key); else next.add(key); return next; })} aria-pressed={expandedGoals.has(`${selected.id}|${type}`)}>{NODE_LABELS[type]} {count}</button> : null; })}</div></section>}
          <section className="network-loops onto-detail-section"><h3>反馈回路（{loopError ? "未载入" : loops.length}）</h3>{loops.map((loop, index) => <button key={loop.loop_id} className={`onto-btn network-loop-card${selectedLoopId === loop.loop_id ? " is-selected" : ""}`} onClick={() => focusLoop(loop)} aria-pressed={selectedLoopId === loop.loop_id}><small>Loop {String(index + 1).padStart(2, "0")}</small><strong>{loop.loop_type === "Reinforcing" ? "增强回路" : "平衡回路"}</strong><span>{loop.nodes.map(nameOf).join(" → ")}{loop.nodes.length ? ` → ${nameOf(loop.nodes[0])}` : ""}</span><small>{loop.status === "CONDITIONAL" ? "条件回路" : "当前有效"} · 置信度 {Math.round(loop.confidence * 100)}%</small></button>)}{!loops.length && !loopError && <p className="network-muted">服务端未返回反馈回路</p>}</section>
        </aside>
      </SideRail>
    </div>
  </div>;
}

export default function GoalNetworkView({ instance, datasetId, loopView, onShowHierarchy }: {
  instance: CogneeInstance; datasetId: string; loopView?: boolean;
  onShowHierarchy?: () => void;
}) {
  const [model, setModel] = useState<GoalModelView | null>(null);
  const [loops, setLoops] = useState<GoalNetworkLoop[]>([]);
  const [error, setError] = useState("");
  const [loopError, setLoopError] = useState("");
  useEffect(() => {
    let active = true;
    setModel(null); setError(""); setLoops([]); setLoopError("");
    if (!datasetId) return;
    void getGoalModel(instance, datasetId).then(result => { if (active) setModel(result); }).catch(cause => { if (active) setError(String(cause.message || cause)); });
    void getGoalNetworkLoops(instance, datasetId).then(result => { if (active) { setLoops(result); } }).catch(cause => { if (active) setLoopError(String(cause.message || cause)); });
    return () => { active = false; };
  }, [instance, datasetId]);
  if (error) return <p role="alert" className="network-error">经营网络无法载入：{error}</p>;
  if (!model) return <p className="network-loading">{datasetId ? "正在载入经营网络…" : "请选择数据集"}</p>;
  return <GoalNetworkPresentation key={datasetId} model={model} loops={loops} loopError={loopError} loopView={loopView} onShowHierarchy={onShowHierarchy} />;
}
