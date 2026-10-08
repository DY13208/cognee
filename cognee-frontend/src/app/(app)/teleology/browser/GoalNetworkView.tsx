"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { CogneeInstance } from "@/modules/instances/types";
import { getGoalModel, getGoalNetworkLoops, type GoalModelView, type GoalNetworkLoop } from "@/modules/teleology/teleologyApi";
import SideRail from "./SideRail";
import { businessName, CAUSAL_RELATIONS, currentNetwork, DEFAULT_TYPES, edgeKey, NETWORK_TYPES, NODE_COLORS, NODE_LABELS, networkType, RELATION_LABELS, sourceOf, targetOf, type NetworkType } from "./goalNetwork";
import "./goalNetwork.css";
import { businessGoals, businessNetwork, canvasProjection, clusteredLayout, companyLayout, connectionAvailability, defaultBusinessGoal, supportingNodes, SUPPORT_TYPES, type NetworkScope } from "./networkProjection";
import NodeCard from "./NodeCard";
import { connectionPath, EDGE_STROKE_WIDTH, EDGE_HIGHLIGHT_WIDTH, EDGE_LABEL_STYLE } from "./edgeAppearance";
import { REL_PILL } from "./entityMeta";
import { NODE_ICONS } from "./goalNetwork";
import { CARD_W } from "./layoutDag";
import { fitCanvasBounds } from "./fitCanvas";

function MeasuredNetworkCard({ id, lod, children, onMeasure }: {
  id: string; lod: string; children: ReactNode;
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
  return <div ref={ref} className="network-node-card">{children}</div>;
}

export function GoalNetworkPresentation({ model, loops, loopError, onShowHierarchy }: {
  model: GoalModelView; loops: GoalNetworkLoop[]; loopError?: string; loopView?: boolean;
  onShowHierarchy?: () => void;
}) {
  const [types, setTypes] = useState<Set<NetworkType>>(() => new Set(model.submission_mode === "patch" ? NETWORK_TYPES : DEFAULT_TYPES));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedLoopId, setSelectedLoopId] = useState<string | null>(null);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [rightTab, setRightTab] = useState<"details" | "loops">("details");
  const [loopQuery, setLoopQuery] = useState("");
  const [loopTypeFilter, setLoopTypeFilter] = useState("all");
  const [expandedLoops, setExpandedLoops] = useState<Set<string>>(() => new Set());
  const loopFocusRequest = useRef<string | null>(null);
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<NetworkScope>("business");
  const [contextScope, setContextScope] = useState<Exclude<NetworkScope, "focus">>("business");
  const [businessGoalId, setBusinessGoalId] = useState<string | null>(() => defaultBusinessGoal(model));
  const [focusId, setFocusId] = useState<string | null>(null);
  const [hops, setHops] = useState<1 | 2 | "all">(1);
  const [showSupport, setShowSupport] = useState(model.submission_mode === "patch");
  const supportAutoTypes = useRef(new Set<NetworkType>());
  const [expandedGoals, setExpandedGoals] = useState<Set<string>>(() => new Set());
  const [zoom, setZoom] = useState(1);
  const [fitCompany, setFitCompany] = useState(false);
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
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (event: WheelEvent) => {
      if (!(event.ctrlKey || event.metaKey) || !event.deltaY) return;
      event.preventDefault();
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? canvas.clientHeight || 700 : 1);
      const factor = Math.exp(-Math.max(-150, Math.min(150, delta)) * .002);
      setZoom(value => Math.max(.4, Math.min(10, value * factor)));
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, []);
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
  const relevantLoops = useMemo(() => {
    const ids = new Set(network.nodes.map(node => node.id));
    return loops.filter(loop => loop.nodes.every(id => ids.has(id)) &&
      (scope !== "focus" || !focusId || loop.nodes.includes(focusId)));
  }, [loops, network, scope, focusId]);
  const selectedLoop = loops.find(loop => loop.loop_id === selectedLoopId) || null;
  const filteredLoops = relevantLoops.filter(loop => {
    const number = `Loop ${String(loops.indexOf(loop) + 1).padStart(2, "0")}`;
    const text = [number, loop.loop_type === "Reinforcing" ? "增强回路" : "平衡回路",
      ...loop.nodes.map(id => businessName(directory.nodes.find(node => node.id === id) || { name: "未载入的节点", description: "" })),
      ...loop.conditions.map(condition => typeof condition === "string" ? condition : JSON.stringify(condition))].join(" ");
    return (loopTypeFilter === "all" || loop.loop_type === loopTypeFilter) && text.toLowerCase().includes(loopQuery.trim().toLowerCase());
  });
  const loopNodes = useMemo(() => new Set(selectedLoop?.nodes || []), [selectedLoop]);
  const loopEdges = useMemo(() => new Set((selectedLoop?.edges || []).map(edgeKey)), [selectedLoop]);
  const projection = useMemo(() => canvasProjection(network, { types, showSupport, expandedGoals, focusId: scope === "focus" ? focusId : null, hops, loopNodes, loopEdges }), [network, types, showSupport, expandedGoals, scope, focusId, hops, loopNodes, loopEdges]);
  const visible = projection.nodes;
  const layout = useMemo(() => scope === "global" ? companyLayout(model, visible, projection.relations, layoutHeights) : clusteredLayout(visible, projection.relations, layoutHeights), [scope, model, visible, projection.relations, layoutHeights]);
  const basePositions = layout.positions;
  const positioned = useMemo(() => basePositions.map(p => ({ ...p, x: p.x + (nodeOffsets[p.node.id]?.x || 0), y: p.y + (nodeOffsets[p.node.id]?.y || 0) })), [basePositions, nodeOffsets]);
  const byId = new Map(positioned.map(position => [position.node.id, position]));
  const relations = projection.relations;
  const selected = directory.nodes.find(node => node.id === selectedId);
  const width = Math.max(920, ...layout.clusters.map(p => p.x + p.width + 20));
  const height = Math.max(600, ...layout.clusters.map(p => p.y + p.height + 20));
  const fitted = useMemo(() => fitCompany ? fitCanvasBounds(positioned.map(position => ({ x: position.x, y: position.y, width: CARD_W, height: Math.max(120, layoutHeights[position.node.id] || 0) })), canvasSize) : null, [fitCompany, positioned, layoutHeights, canvasSize]);
  const viewportWidth = fitted?.width ?? (scope === "global" ? canvasSize.width : width);
  const viewportHeight = fitted?.height ?? (scope === "global" ? canvasSize.height : height);
  const displayScale = zoom * Math.min(canvasSize.width / viewportWidth, canvasSize.height / viewportHeight);
  const lod = displayScale < .65 ? "far" : displayScale < 1.15 ? "medium" : "near";
  const minimumHeight = lod === "far" ? 56 : lod === "near" ? 120 : 80;
  const heightOf = useCallback((id: string) => nodeHeights[`${id}|${lod}`] || minimumHeight, [nodeHeights, lod, minimumHeight]);
  useLayoutEffect(() => {
    if (!selectedLoop || loopFocusRequest.current !== selectedLoop.loop_id) return;
    const members = positioned.filter(position => selectedLoop.nodes.includes(position.node.id));
    if (members.length !== selectedLoop.nodes.length || !members.length) return;
    loopFocusRequest.current = null;
    const left = Math.min(...members.map(p => p.x)), top = Math.min(...members.map(p => p.y));
    const right = Math.max(...members.map(p => p.x + CARD_W));
    const bottom = Math.max(...members.map(p => p.y + heightOf(p.node.id)));
    const nextZoom = Math.max(.4, Math.min(10, .85 * Math.min(viewportWidth / (right - left + 80), viewportHeight / (bottom - top + 80))));
    setZoom(nextZoom);
    setPan({ x: nextZoom * (viewportWidth / 2 - (left + right) / 2), y: nextZoom * (viewportHeight / 2 - (top + bottom) / 2) });
  }, [selectedLoop, positioned, viewportWidth, viewportHeight, heightOf]);
  const incident = selected ? network.relations.filter(edge => sourceOf(edge) === selected.id || targetOf(edge) === selected.id) : [];
  const availability = connectionAvailability(network, scope === "focus" ? focusId : null);
  const outsideScope = scope === "focus" && !availability.total && connectionAvailability(directory, focusId).total > 0;
  const nameOf = (id: string) => { const node = directory.nodes.find(n => n.id === id); return node ? businessName(node) : "未载入的节点"; };
  function pickNode(id: string, fromDirectory = false) {
    setRightTab("details");
    setSelectedId(id); setRightOpen(true); setSelectedLoopId(null);
    const node = directory.nodes.find(n => n.id === id);
    if (fromDirectory && node && networkType(node) === "goal") {
      const parent = directory.nodes.find(candidate => candidate.id === node.parent_candidate_id);
      const rootId = parent && /^提升 .+ 项目盈利能力$/.test(businessName(parent)) ? parent.id : id;
      setBusinessGoalId(rootId); setContextScope("business"); setScope("business"); setFocusId(null);
      setHops("all"); setTypes(new Set(NETWORK_TYPES)); setShowSupport(true);
      supportAutoTypes.current.clear(); setExpandedGoals(new Set());
      setZoom(1); setPan({ x: 0, y: 0 });
      return;
    }
    if (!network.nodes.some(n => n.id === id)) {
      const owner = anchors.find(n => businessNetwork(model, n.id).nodes.some(member => member.id === id));
      if (owner) { setBusinessGoalId(owner.id); setContextScope("business"); } else setContextScope("global");
    }
    setFocusId(id); setScope("focus"); setHops(1); setZoom(1); setPan({ x: 0, y: 0 });
  }
  function changeScope(next: NetworkScope) {
    setScope(next); setFitCompany(false); setSelectedLoopId(null); setExpandedGoals(new Set()); setZoom(1); setPan({ x: 0, y: 0 });
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
    setFitCompany(false);
    loopFocusRequest.current = loop.loop_id;
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
          <select aria-label="当前业务 Goal" value={businessGoalId || ""} onChange={e => pickNode(e.target.value, true)} className="network-scope">{anchors.length ? [...new Map([...anchors, ...directory.nodes.filter(node => node.id === businessGoalId)].map(node => [node.id, node])).values()].map(node => <option key={node.id} value={node.id}>{businessName(node)}</option>) : <option value={businessGoalId || ""}>{businessGoalId ? nameOf(businessGoalId) : "暂无业务 Goal"}</option>}</select>
          <input className="onto-nav-search" aria-label="搜索业务节点" placeholder="搜索业务名称" value={query} onChange={e => setQuery(e.target.value)} />
          {NETWORK_TYPES.map(type => {
            const scopeIds = new Set(network.nodes.map(n => n.id));
            const nodes = directory.nodes.filter(node => networkType(node) === type).sort((a, b) => Number(scopeIds.has(b.id)) - Number(scopeIds.has(a.id)));
            return <details key={type} open={DEFAULT_TYPES.includes(type) ? true : undefined} className="network-nav-group">
              <summary><span className="onto-file-chevron" aria-hidden><svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M3.2 1.6L6.8 5L3.2 8.4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" /></svg></span><i style={{ background: NODE_COLORS[type] }} />{type === "goal" ? "经营目标" : NODE_LABELS[type]}<span className="onto-nav-count">{nodes.length}</span></summary>
              {nodes.filter(n => businessName(n).includes(query)).map(node => <div key={node.id} className={`onto-file-row network-nav-row${selectedId === node.id ? " is-selected" : ""}`}><button className="onto-file-name network-nav-node" onClick={() => pickNode(node.id, true)}>{businessName(node)}</button></div>)}
              {nodes.length === 0 && <p className="network-muted">暂无节点</p>}
            </details>;
          })}
        </aside>
      </SideRail>
      <main className="onto-canvas-shell network-main">
        <div className="network-controls"><div className="network-type-filters" role="group" aria-label="画布节点类型筛选">{NETWORK_TYPES.map(type => <button key={type} aria-pressed={types.has(type)} className={`onto-btn${types.has(type) ? " is-active" : ""}`} onClick={() => toggle(type)}><i style={{ background: NODE_COLORS[type] }} />{NODE_LABELS[type]}</button>)}</div><span className="network-muted">显示 {visible.length} / {network.nodes.length}</span></div>
        <div className="network-context-bar"><span>{contextScope === "business" ? `当前业务范围 · ${nameOf(businessGoalId || "")}` : contextScope === "pilot" ? "当前 Network Pilot" : "公司全局"} · {relations.length} 条可见关系</span><label><input type="checkbox" checked={showSupport} onChange={e => toggleSupport(e.target.checked)} />显示支撑关系</label>{scope === "focus" && <><strong>Focus · {nameOf(focusId || "")}</strong><div role="group" aria-label="Focus 跳数">{([1, 2, "all"] as const).map(hop => <button className="onto-btn" key={hop} aria-pressed={hops === hop} onClick={() => setHops(hop)}>{hop === "all" ? "全部" : `${hop}跳`}</button>)}</div><button className="onto-btn" onClick={() => changeScope(contextScope)}>退出 Focus</button></>}</div>
        {loopError && <p role="alert" className="network-error">反馈回路暂时无法载入：{loopError}</p>}
        {scope === "global" && <div className="network-loop-strip" role="group" aria-label="公司分区定位"><strong>定位分区</strong>{layout.clusters.map(cluster => <button className="onto-btn" key={cluster.name} onClick={() => { setFitCompany(false); setZoom(1); setPan({ x: 20 - cluster.x, y: 20 - cluster.y }); }}>{cluster.name}</button>)}<span className="network-muted">默认原比例 · 拖动画布查看 · 适应画布查看全图</span></div>}
        <div ref={canvasRef} className={`network-canvas lod-${lod}`} data-lod={lod} title="Ctrl + 鼠标滚轮缩放（Mac：⌘ + 滚轮）">
          <svg aria-label="经营关系网络画布" viewBox={`0 0 ${viewportWidth} ${viewportHeight}`} onPointerDown={e => { if ((e.target as Element).closest(".network-node")) return; drag.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y }; e.currentTarget.setPointerCapture(e.pointerId); }} onPointerMove={e => { if (drag.current) { const bounds = e.currentTarget.getBoundingClientRect(); const ratio = Math.max(viewportWidth / bounds.width, viewportHeight / bounds.height); setPan({ x: drag.current.panX + (e.clientX - drag.current.x) * ratio, y: drag.current.panY + (e.clientY - drag.current.y) * ratio }); } }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
            <defs><marker id="network-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="rgba(232,231,228,0.35)" /></marker><marker id="network-arrow-hi" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="rgba(232,231,228,0.75)" /></marker></defs>
            <g ref={graphRef} transform={`translate(${pan.x + viewportWidth * (1 - zoom) / 2 + zoom * (fitted?.offsetX || 0)},${pan.y + viewportHeight * (1 - zoom) / 2 + zoom * (fitted?.offsetY || 0)}) scale(${zoom})`}>
              {layout.clusters.map(cluster => <g key={cluster.name} className="network-cluster" opacity={selectedLoop ? .08 : 1}><text role={"rootId" in cluster && cluster.rootId ? "button" : undefined} tabIndex={"rootId" in cluster && cluster.rootId ? 0 : undefined} onPointerDown={e => e.stopPropagation()} onClick={() => { if ("rootId" in cluster && typeof cluster.rootId === "string") { setBusinessGoalId(cluster.rootId); changeScope("business"); } }} onKeyDown={e => { if ((e.key === "Enter" || e.key === " ") && "rootId" in cluster && typeof cluster.rootId === "string") { e.preventDefault(); setBusinessGoalId(cluster.rootId); changeScope("business"); } }} x={cluster.x + 20} y={cluster.y + 12} style={{ fontSize: Math.min(30, Math.max(12, 12 / displayScale)) }}>{cluster.name}</text><path d={`M${cluster.x + 20},${cluster.y + 20}H${cluster.x + cluster.width - 20}`} /></g>)}
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
                <MeasuredNetworkCard id={node.id} lod={lod} onMeasure={measureNode}>
                <NodeCard name={businessName(node)} color={NODE_COLORS[networkType(node)]}
                  icon={NODE_ICONS[networkType(node)]} label={NODE_LABELS[networkType(node)]}
                  appearance={{ focus: loopNodes.has(node.id) || focusId === node.id, selected: selectedId === node.id, proposed: node.status === "proposed", semantic: networkType(node) === "constraint" }}
                  showDetails={lod === "near"} meta={node.description || node.reason || "暂无说明"} metaClassName="network-node-description"
                  counts={<span className="network-node-degree">关系 {network.relations.filter(e => sourceOf(e) === node.id || targetOf(e) === node.id).length}</span>}
                  interactiveProps={{ className: `network-node${selectedId === node.id ? " is-selected" : ""}${loopNodes.has(node.id) ? " is-loop" : ""}`,
                  onPointerDown: e => {
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
                  },
                  onPointerMove: e => {
                    const active = nodeDrag.current;
                    if (!active || active.id !== node.id || active.pointerId !== e.pointerId) return;
                    e.stopPropagation();
                    const point = new DOMPoint(e.clientX, e.clientY).matrixTransform(active.inverse);
                    const dx = point.x - active.x, dy = point.y - active.y;
                    if (!nodeMoved.current && Math.hypot(dx, dy) < 4) return;
                    nodeMoved.current = true;
                    setNodeOffsets(old => ({ ...old, [node.id]: { x: active.offsetX + dx, y: active.offsetY + dy } }));
                  },
                  onPointerUp: e => { e.stopPropagation(); nodeDrag.current = null; },
                  onPointerCancel: () => { nodeDrag.current = null; },
                  onLostPointerCapture: () => { nodeDrag.current = null; },
                  onKeyDown: e => {
                    const delta: Record<string, [number, number]> = { ArrowLeft: [-20, 0], ArrowRight: [20, 0], ArrowUp: [0, -20], ArrowDown: [0, 20] };
                    if (!delta[e.key]) return;
                    e.preventDefault(); e.stopPropagation();
                    const [dx, dy] = delta[e.key];
                    setNodeOffsets(old => ({ ...old, [node.id]: { x: (old[node.id]?.x || 0) + dx, y: (old[node.id]?.y || 0) + dy } }));
                  },
                  onClick: () => { if (nodeMoved.current) { nodeMoved.current = false; return; } pickNode(node.id); }, onKeyUp: e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pickNode(node.id); } }, title: "点击进入 Focus，拖动移动节点；方向键微调位置", "aria-label": `${NODE_LABELS[networkType(node)]}：${businessName(node)}` }}
                  footer={lod !== "far" && networkType(node) === "goal" && <div className="network-support-badges">{SUPPORT_TYPES.map(type => { const count = supportingNodes(node.id, network, type).length; return count ? <button className="onto-btn" key={type} aria-label={`${businessName(node)}展开附属${NODE_LABELS[type]}`} aria-pressed={expandedGoals.has(`${node.id}|${type}`)} onPointerDown={e => e.stopPropagation()} onClick={() => setExpandedGoals(old => { const next = new Set(old); const key = `${node.id}|${type}`; if (next.has(key)) next.delete(key); else next.add(key); return next; })}>{NODE_LABELS[type]} {count}</button> : null; })}</div>} />
                </MeasuredNetworkCard>
              </foreignObject>)}
            </g>
          </svg>
          {!visible.length && <div className="teleology-canvas-empty network-empty" role="status">
            {availability.total ? <><strong>已有 {availability.total} 条关系，被当前筛选隐藏</strong><p>因果关系 {availability.causal} 条 · 支撑关系 {availability.supporting} 条。关系端点的节点类型也需要显示。</p><button className="onto-btn" onClick={revealConnections}>{scope === "focus" ? "显示该节点的关联关系" : "显示当前范围的关联关系"}</button></>
              : outsideScope ? <><strong>该节点的关系位于当前业务范围之外</strong><p>当前范围没有相连节点，可切换范围查看已有关系。</p><button className="onto-btn" onClick={() => changeScope("global")}>查看公司全局</button></>
              : <><strong>{scope === "focus" ? "该节点尚未建立经营影响关系" : "当前业务范围尚未建立经营影响关系"}</strong><p>目标层级与来源证据不会被用来填充经营网络。</p>{onShowHierarchy && <button className="onto-btn" onClick={onShowHierarchy}>查看目标层级</button>}</>}
          </div>}
          <div className="network-zoom"><button className="onto-btn" aria-label="缩小网络" onClick={() => setZoom(v => Math.max(.4, v - .15))}>−</button><span>{Math.round(zoom * 100)}%</span><button className="onto-btn" aria-label="放大网络" onClick={() => setZoom(v => Math.min(10, v + .15))}>＋</button><button className="onto-btn" onClick={() => { setFitCompany(true); setZoom(1); setPan({ x: 0, y: 0 }); }}>适应画布</button></div>
        </div>
        <footer className="network-legend"><span><i />因果关系</span><span><i className="is-structural" />非因果关系</span><span>拖动节点调整位置 · 拖动画布平移 · 点击节点查看详情</span></footer>
      </main>
      <SideRail side="right" open={rightOpen} onOpen={() => setRightOpen(true)} expandLabel="展开网络详情">
        <aside className="onto-detail network-detail">
          <div className="network-panel-header onto-detail-head">
            <div className="network-panel-tabs" role="tablist" aria-label="网络右侧面板">
              <button id="network-details-tab" role="tab" className="onto-btn" aria-selected={rightTab === "details"} aria-controls="network-details-panel" onClick={() => setRightTab("details")}>节点详情</button>
              <button id="network-loops-tab" role="tab" className="onto-btn" aria-selected={rightTab === "loops"} aria-controls="network-loops-panel" onClick={() => setRightTab("loops")}>反馈回路（{loopError ? "未载入" : relevantLoops.length}）</button>
            </div>
            <button className="onto-panel-close" onClick={() => setRightOpen(false)} aria-label="收起网络详情">×</button>
          </div>
          {rightTab === "details" ? <div id="network-details-panel" role="tabpanel" aria-labelledby="network-details-tab">

          {selected ? <><span className="network-kind onto-detail-kind" style={{ color: NODE_COLORS[networkType(selected)] }}>{NODE_LABELS[networkType(selected)]}</span><h2 className="onto-detail-title">{businessName(selected)}</h2><p>{selected.description}</p><h3>理由</h3><p>{selected.reason || "暂无说明"}</p><p className="network-muted">置信度 {Math.round((selected.confidence || 0) * 100)}% · {(selected.evidence || []).length} 条证据</p><h3>关联关系（{incident.length}）</h3>{incident.map(edge => <div className="network-detail-edge" key={edge.id || edgeKey(edge)}><span>{nameOf(sourceOf(edge))} <b>{RELATION_LABELS[edge.relationship || ""] || "其他关系"} →</b> {nameOf(targetOf(edge))}</span>{edge.condition != null && <small>条件：{typeof edge.condition === "object" ? edge.condition.expression || "由服务端判定" : typeof edge.condition === "boolean" ? edge.condition ? "已满足" : "未满足" : edge.condition}</small>}</div>)}</> : <><h2>经营网络</h2><p className="network-muted">画布展示当前业务中的有效连接。完整节点目录保留在左侧，点击节点进入 1 跳 Focus。</p></>}
          <section className="network-isolated onto-detail-section"><h3>未参与当前网络（{projection.isolated.length}）</h3><p className="network-muted">未进入当前画布的节点，点击查看详情与已有关系。</p>{projection.isolated.map(node => <button className="onto-file-name" key={node.id} onClick={() => { setSelectedId(node.id); setRightTab("details"); setRightOpen(true); }}>{NODE_LABELS[networkType(node)]} · {businessName(node)}<small>{connectionAvailability(network, node.id).total ? "已有关系，被当前筛选隐藏" : "尚未建立经营影响关系"}</small></button>)}</section>
          {selected && networkType(selected) === "goal" && <section><h3>附属信息</h3><div className="network-support-badges">{SUPPORT_TYPES.map(type => { const count = supportingNodes(selected.id, network, type).length; return count ? <button className="onto-btn" key={type} onClick={() => setExpandedGoals(old => { const next = new Set(old); const key = `${selected.id}|${type}`; if (next.has(key)) next.delete(key); else next.add(key); return next; })} aria-pressed={expandedGoals.has(`${selected.id}|${type}`)}>{NODE_LABELS[type]} {count}</button> : null; })}</div></section>}
          </div> : <div id="network-loops-panel" role="tabpanel" aria-labelledby="network-loops-tab" className="network-loops">
            <div className="network-loop-tools">
              <input className="onto-nav-search" aria-label="搜索反馈回路" placeholder="搜索反馈回路" value={loopQuery} onChange={e => setLoopQuery(e.target.value)} />
              <div className="network-loop-tool-row">
                <select className="network-scope" aria-label="反馈回路类型" value={loopTypeFilter} onChange={e => setLoopTypeFilter(e.target.value)}>
                  <option value="all">全部类型</option><option value="Reinforcing">增强回路</option><option value="Balancing">平衡回路</option>
                </select>
                <button className="onto-btn" onClick={() => setExpandedLoops(old => new Set([...old, ...filteredLoops.map(loop => loop.loop_id)]))}>展开全部</button>
              </div>
            </div>
            {loopError && <p role="alert" className="network-error">{loopError}</p>}
            {filteredLoops.map(loop => <article key={loop.loop_id} className={`network-loop-card${selectedLoopId === loop.loop_id ? " is-selected" : ""}`}>
              <div className="network-loop-card-head">
                <button className="network-loop-select" onClick={() => focusLoop(loop)} aria-pressed={selectedLoopId === loop.loop_id}>
                  <small>Loop {String(loops.indexOf(loop) + 1).padStart(2, "0")}</small><strong>{loop.loop_type === "Reinforcing" ? "增强回路" : "平衡回路"}</strong>
                </button>
                <button className="onto-btn" aria-label={`${expandedLoops.has(loop.loop_id) ? "收起" : "展开"} Loop ${String(loops.indexOf(loop) + 1).padStart(2, "0")}`} aria-expanded={expandedLoops.has(loop.loop_id)} aria-controls={`network-loop-${loop.loop_id}`} onClick={() => setExpandedLoops(old => { const next = new Set(old); if (next.has(loop.loop_id)) next.delete(loop.loop_id); else next.add(loop.loop_id); return next; })}>{expandedLoops.has(loop.loop_id) ? "−" : "＋"}</button>
              </div>
              <small>{loop.status === "CONDITIONAL" ? "条件回路" : "当前有效"} · 置信度 {Math.round(loop.confidence * 100)}%</small>
              {expandedLoops.has(loop.loop_id) && <div id={`network-loop-${loop.loop_id}`} className="network-loop-card-body">
                <span>{loop.nodes.map(nameOf).join(" → ")}{loop.nodes.length ? ` → ${nameOf(loop.nodes[0])}` : ""}</span>
                {loop.conditions.map((condition, i) => <p key={i}>条件：{typeof condition === "string" ? condition : typeof condition === "object" && condition !== null && "expression" in condition ? String(condition.expression) : JSON.stringify(condition)}</p>)}
              </div>}
            </article>)}
            {!filteredLoops.length && !loopError && <p className="network-muted">{relevantLoops.length ? "没有匹配的反馈回路" : "当前范围没有反馈回路"}</p>}
            {selectedLoop && <button className="onto-btn" onClick={() => setSelectedLoopId(null)}>取消高亮</button>}
          </div>}

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
