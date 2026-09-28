"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CogneeInstance } from "@/modules/instances/types";
import { createGraphAnnotation, createWorkspaceGoal, deleteWorkspaceGoal, getGoalDetail, getGoalPath, getGoalRelations, getGraphAnnotations, moveWorkspaceGoal, syncTeleologyFromCompanyTree, syncTeleologyGoals, updateWorkspaceGoal, type GraphAnnotation, type GraphNodeSummary } from "@/modules/teleology/teleologyApi";
import { notifications } from "@mantine/notifications";
import NavPanel, { type GoalPage } from "./NavPanel";
import DetailPanel from "./DetailPanel";
import { displayName } from "./entityMeta";
import type { OntologyEdge, OntologyEntity } from "./types";
import "./ontology.css";

type DatasetOpt = { id: string; name: string };
const PAGE = 30;
const CANVAS_PAGE = 17;
function entity(goal: GraphNodeSummary): OntologyEntity {
  return { id: goal.id, name: displayName(goal.name, goal.id), type: goal.type || "Goal", kind: "Goal", description: goal.description, status: goal.status, parentName: goal.parent_name, childCount: goal.child_count || 0, owner: goal.owner, createdAt: goal.created_at, progress: goal.progress, source: goal.source };
}
function edges(annotations: GraphAnnotation[]): OntologyEdge[] {
  return annotations.map((annotation) => ({ id: `${annotation.source_id}|${annotation.relationship}|${annotation.target_id}`, sourceId: annotation.source_id, targetId: annotation.target_id, sourceName: annotation.source_name, targetName: annotation.target_name, sourceType: annotation.source_type, targetType: annotation.target_type, relationship: annotation.relationship }));
}

export default function OntologyBrowser({ instance, datasets, selectedDataset, onSelectDataset, language, busy, onBusy, onHeaderCollapsedChange }: {
  instance: CogneeInstance; datasets: DatasetOpt[]; selectedDataset: DatasetOpt | null; onSelectDataset: (dataset: DatasetOpt) => void;
  language: "zh" | "en"; busy: boolean; onBusy: (value: boolean) => void; onHeaderCollapsedChange?: (collapsed: boolean) => void;
}) {
  const t = (en: string, zh: string) => language === "zh" ? zh : en;
  const datasetId = selectedDataset?.id || datasets[0]?.id || "";
  const [roots, setRoots] = useState<GraphNodeSummary[]>([]);
  const [rootTotal, setRootTotal] = useState(0);
  const [pages, setPages] = useState<Record<string, GoalPage>>({});
  const pagesRef = useRef(pages);
  pagesRef.current = pages;
  const [focusId, setFocusId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focus, setFocusGoal] = useState<GraphNodeSummary | null>(null);
  const [parent, setParent] = useState<GraphNodeSummary | null>(null);
  const [path, setPath] = useState<GraphNodeSummary[]>([]);
  const [children, setChildren] = useState<GraphNodeSummary[]>([]);
  const [childTotal, setChildTotal] = useState(0);
  const [relations, setRelations] = useState<OntologyEdge[]>([]);
  const [relationCounts, setRelationCounts] = useState({ serves: 0, advances: 0, blocks: 0 });
  const [relationTotal, setRelationTotal] = useState(0);
  const [relationOffset, setRelationOffset] = useState(0);
  const [relationType, setRelationType] = useState<"serves" | "advances" | "blocks" | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<"children" | "path" | "relations" | null>(null);
  const [drawerPath, setDrawerPath] = useState<GraphNodeSummary[]>([]);
  const [drawerQuery, setDrawerQuery] = useState("");
  const [drawerPage, setDrawerPage] = useState<GraphNodeSummary[]>([]);
  const [drawerTotal, setDrawerTotal] = useState(0);
  const [drawerOffset, setDrawerOffset] = useState(0);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [topOpen, setTopOpen] = useState(true);
  const [datasetMenu, setDatasetMenu] = useState(false);
  const [view, setView] = useState<"focus" | "tree">("focus");
  const requestId = useRef(0);

  const loadPath = useCallback((goal: GraphNodeSummary) => getGoalPath(instance, datasetId, goal.id), [instance, datasetId]);

  const enter = useCallback(async (id: string) => {
    if (!datasetId) return;
    const serial = ++requestId.current;
    setLoading(true); setError(null);
    try {
      const [current, childPage, relationPage, chain] = await Promise.all([
        getGoalDetail(instance, datasetId, id),
        getGraphAnnotations(instance, datasetId, { parentId: id, goalsLimit: CANVAS_PAGE }),
        getGoalRelations(instance, datasetId, id, { limit: 30 }),
        getGoalPath(instance, datasetId, id),
      ]);
      if (serial !== requestId.current) return;
      const parentGoal = chain.length > 1 ? chain[chain.length - 2] : null;
      const visibleChildren = childPage.goals.slice(0, (childPage.goals_total || 0) > 16 ? 12 : 16);
      if (chain[0]) setRoots((old) => old.some((root) => root.id === chain[0].id) ? old : [...old, chain[0]]);
      setFocusId(id); setSelectedId(id); setFocusGoal(current); setParent(parentGoal); setPath(chain);
      setChildren(visibleChildren); setChildTotal(childPage.goals_total ?? childPage.goals.length);
      setRelations(edges(relationPage.items)); setRelationCounts(relationPage.counts);
      setPages((old) => {
        const next = { ...old };
        chain.slice(0, -1).forEach((ancestor, index) => {
          const child = chain[index + 1];
          const page = next[ancestor.id];
          if (!page) next[ancestor.id] = { items: [child], total: ancestor.child_count || 1, loading: false, loaded: false, nextOffset: 0 };
          else if (!page.items.some((item) => item.id === child.id)) next[ancestor.id] = { ...page, items: [...page.items, child] };
        });
        if (!next[id]?.loaded) next[id] = { items: childPage.goals, total: childPage.goals_total ?? childPage.goals.length, loading: false, loaded: true, nextOffset: childPage.goals.length };
        return next;
      });
    } catch (cause) { if (serial === requestId.current) setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { if (serial === requestId.current) setLoading(false); }
  }, [instance, datasetId]);

  const loadRoots = useCallback(async () => {
    if (!datasetId) return;
    setLoading(true); setError(null);
    try {
      const result = await getGraphAnnotations(instance, datasetId, { parentId: "_roots", goalsLimit: PAGE });
      setRoots(result.goals); setRootTotal(result.goals_total ?? result.goals.length);
      if (result.goals.length) await enter(result.goals[0].id);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); setLoading(false); }
  }, [instance, datasetId, enter]);

  useEffect(() => {
    requestId.current += 1; setRoots([]); setPages({}); setFocusId(null); setSelectedId(null); setFocusGoal(null); setParent(null); setPath([]); setChildren([]); setRelations([]);
    if (datasetId) void loadRoots();
  }, [datasetId, loadRoots]);

  const expand = useCallback(async (id: string, more = false) => {
    const prior = pagesRef.current[id];
    if (prior?.loading || (!more && prior?.loaded)) return;
    const offset = more ? prior?.nextOffset || 0 : 0;
    setPages((old) => ({ ...old, [id]: { items: old[id]?.items || [], total: old[id]?.total || 0, loaded: old[id]?.loaded, nextOffset: old[id]?.nextOffset || 0, loading: true } }));
    try {
      const result = await getGraphAnnotations(instance, datasetId, { parentId: id, goalsLimit: PAGE, goalsOffset: offset });
      setPages((old) => {
        const items = [...(old[id]?.items || []), ...result.goals];
        return { ...old, [id]: { items: items.filter((item, index) => items.findIndex((candidate) => candidate.id === item.id) === index), total: result.goals_total ?? offset + result.goals.length, loading: false, loaded: true, nextOffset: offset + result.goals.length } };
      });
    } catch (cause) { setPages((old) => ({ ...old, [id]: { ...old[id], loading: false } })); setError(cause instanceof Error ? cause.message : String(cause)); }
  }, [instance, datasetId]);

  const search = useCallback(async (query: string) => {
    const result = await getGraphAnnotations(instance, datasetId, { q: query, goalsLimit: PAGE, limit: 1 });
    return result.goals;
  }, [instance, datasetId]);

  useEffect(() => {
    if (drawer !== "children" || !focusId) return;
    let active = true;
    const timer = window.setTimeout(() => {
      setDrawerLoading(true);
      void getGraphAnnotations(instance, datasetId, { parentId: focusId, q: drawerQuery || undefined, goalsLimit: PAGE, goalsOffset: drawerOffset }).then((result) => {
        if (!active) return;
        setDrawerPage(result.goals); setDrawerTotal(result.goals_total ?? result.goals.length);
      }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : String(cause)); }).finally(() => { if (active) setDrawerLoading(false); });
    }, drawerQuery ? 250 : 0);
    return () => { active = false; window.clearTimeout(timer); };
  }, [drawer, drawerQuery, drawerOffset, focusId, instance, datasetId]);

  useEffect(() => {
    if (drawer !== "relations" || !focusId) return;
    let active = true;
    setDrawerLoading(true);
    void getGoalRelations(instance, datasetId, focusId, { relationship: relationType, offset: relationOffset, limit: PAGE }).then((result) => {
      if (!active) return;
      setRelations(edges(result.items)); setRelationCounts(result.counts); setRelationTotal(result.total);
    }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : String(cause)); }).finally(() => { if (active) setDrawerLoading(false); });
    return () => { active = false; };
  }, [drawer, focusId, relationOffset, relationType, instance, datasetId]);

  const selectedEntity = useMemo(() => {
    const found = [focus, parent, ...children, ...path, ...roots].find((goal) => goal?.id === selectedId);
    if (found) return entity(found);
    const relation = relations.find((edge) => edge.sourceId === selectedId || edge.targetId === selectedId);
    if (!relation || !selectedId) return null;
    return { id: selectedId, name: relation.sourceId === selectedId ? relation.sourceName : relation.targetName, type: "Goal", kind: "Goal" as const };
  }, [focus, parent, children, path, roots, selectedId, relations]);

  async function viewSelectedPath() {
    try {
      let goal = [focus, parent, ...children, ...path, ...roots].find((item) => item?.id === selectedId);
      if (!goal && selectedId) {
        goal = await getGoalDetail(instance, datasetId, selectedId);
      }
      if (!goal) return;
      setDrawerPath(await loadPath(goal));
      setDrawer("path");
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
  }

  async function runGoalAction(action: () => Promise<string | void>, nextId?: string) {
    try {
      const resultId = await action();
      setPages({});
      if (resultId || nextId) await enter(resultId || nextId!);
      else if (focusId) await enter(focusId);
      notifications.show({ title: t("Goal updated", "目标已更新"), message: "", color: "green" });
    } catch (cause) { notifications.show({ title: t("Operation failed", "操作失败"), message: cause instanceof Error ? cause.message : String(cause), color: "red" }); }
  }

  function createChild(id: string) {
    const name = window.prompt(t("New subgoal name", "新子目标名称"))?.trim();
    if (!name) return;
    void runGoalAction(async () => {
      const created = await createWorkspaceGoal(instance, datasetId, { parentId: id, name });
      return created.id;
    });
  }

  function relateGoal(id: string) {
    const targetId = window.prompt(t("Related goal ID", "关联目标 ID"))?.trim();
    if (!targetId) return;
    const relationship = window.prompt(t("Relationship: serves / advances / blocks", "关系类型：serves / advances / blocks"), "serves")?.trim();
    if (relationship !== "serves" && relationship !== "advances" && relationship !== "blocks") return;
    void runGoalAction(async () => { await createGraphAnnotation(instance, { datasetId, sourceId: id, targetId, relationship }); });
  }

  function copyGoal(id: string) {
    void runGoalAction(async () => {
      const [goal, chain] = await Promise.all([getGoalDetail(instance, datasetId, id), getGoalPath(instance, datasetId, id)]);
      const parentId = chain.length > 1 ? chain[chain.length - 2].id : focusId;
      if (!parentId || parentId === id) throw new Error(t("Choose a parent goal first", "请先选择上级目标"));
      const copy = await createWorkspaceGoal(instance, datasetId, { parentId, name: `${goal.name} ${t("copy", "副本")}`, description: goal.description });
      return copy.id;
    });
  }

  function editGoal(id: string) {
    const name = window.prompt(t("Goal name", "目标名称"), selectedEntity?.name)?.trim();
    if (!name) return;
    void runGoalAction(async () => { await updateWorkspaceGoal(instance, datasetId, id, { name }); });
  }

  function moveGoal(id: string) {
    const parentId = window.prompt(t("New parent goal ID", "新上级目标 ID"))?.trim();
    if (!parentId) return;
    void runGoalAction(async () => { await moveWorkspaceGoal(instance, datasetId, id, parentId); }, id);
  }

  function removeGoal(id: string) {
    if (!window.confirm(t("Delete this goal?", "确定删除此目标？"))) return;
    const nextId = id === focusId ? parent?.id : focusId || undefined;
    void runGoalAction(async () => { await deleteWorkspaceGoal(instance, datasetId, id); }, nextId);
  }

  function exportGoal(id: string) {
    void Promise.all([getGoalDetail(instance, datasetId, id), getGoalRelations(instance, datasetId, id, { limit: 100 })]).then(([goal, purpose]) => {
      const blob = new Blob([JSON.stringify({ goal, purpose, relations_truncated: purpose.total > purpose.items.length }, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a"); link.href = url; link.download = `goal-${id}.json`; link.click();
      URL.revokeObjectURL(url);
    }).catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)));
  }

  async function syncTree() {
    onBusy(true);
    try { const result = await syncTeleologyFromCompanyTree(instance, datasetId); notifications.show({ title: t("Synced", "已同步"), message: `${result.tree_goals} ${t("goals", "个目标")}`, color: "green" }); setPages({}); await loadRoots(); }
    catch (cause) { notifications.show({ title: t("Sync failed", "同步失败"), message: cause instanceof Error ? cause.message : String(cause), color: "red" }); }
    finally { onBusy(false); }
  }
  async function syncYaml() {
    onBusy(true);
    try { await syncTeleologyGoals(instance, datasetId); notifications.show({ title: t("YAML synced", "YAML 已同步"), message: t("Vocabulary written to graph.", "词汇表已写入图谱。"), color: "green" }); }
    catch (cause) { notifications.show({ title: t("Sync failed", "同步失败"), message: cause instanceof Error ? cause.message : String(cause), color: "red" }); }
    finally { onBusy(false); }
  }

  return <div className="onto-root">
    <header className={`onto-top${topOpen ? "" : " is-collapsed"}`}>
      {topOpen ? <>
        <div style={{ position: "relative" }}><button type="button" className="onto-select" onClick={() => setDatasetMenu(!datasetMenu)}>{selectedDataset?.name || datasets[0]?.name || t("No dataset", "暂无数据集")} ▾</button>
          {datasetMenu && <div className="onto-search-menu">{datasets.map((dataset) => <button type="button" className="onto-search-item" key={dataset.id} onClick={() => { onSelectDataset(dataset); setDatasetMenu(false); }}>{dataset.name}</button>)}</div>}
        </div>
        <button type="button" className="onto-btn onto-btn-primary" title={t("Refresh this goal's purpose relationships", "刷新当前目标的目的关系")} disabled={!focusId || loading} onClick={() => { if (focusId) void enter(focusId); }}>{t("Generate purpose relations", "生成目的关系")}</button>
        <button type="button" className="onto-btn" disabled={busy || !datasetId} onClick={() => void syncTree()}>{t("Sync goal tree", "同步目标树")}</button>
        <button type="button" className="onto-btn" disabled={busy || !datasetId} onClick={() => void syncYaml()}>{t("Sync YAML", "同步 YAML")}</button>
        <div className="onto-view-switch"><button type="button" className={view === "focus" ? "is-active" : ""} onClick={() => setView("focus")}>{t("Focus view", "聚焦视图")}</button><button type="button" className={view === "tree" ? "is-active" : ""} onClick={() => setView("tree")}>{t("Tree overview", "树图概览")}</button></div>
      </> : <span className="onto-collapsed-title">{t("Teleology", "目的论")} · {selectedDataset?.name || datasets[0]?.name}</span>}
      <button type="button" className="onto-btn onto-collapse-btn" onClick={() => { setTopOpen(!topOpen); onHeaderCollapsedChange?.(topOpen); }}>{topOpen ? t("Collapse ↑", "收起 ↑") : t("Expand ↓", "展开 ↓")}</button>
    </header>
    <div className="onto-body">
      <div className={`onto-side-container onto-side-left${leftOpen ? "" : " is-collapsed"}`}>
        {leftOpen && <NavPanel language={language} roots={roots} pages={pages} focusId={focusId} pathIds={path.map((goal) => goal.id)} loading={loading} onPick={(id) => void enter(id)} onExpand={expand} onSearch={search} />}
        <button type="button" className="onto-seam-tab onto-seam-tab-left" onClick={() => setLeftOpen(!leftOpen)}>{leftOpen ? "‹" : "›"}</button>
      </div>
      <main className="onto-main onto-focus-main">
        {error && <div className="onto-focus-error" role="alert">{error}</div>}
        <div className="onto-breadcrumb">{path.map((goal, index) => <span key={goal.id}><button type="button" onClick={() => void enter(goal.id)}>{goal.name}</button>{index < path.length - 1 && <b>›</b>}</span>)}</div>
        {view === "focus" ? <div className="onto-focus-scroll">
          {focus && <>
            {parent && <div className="onto-focus-parent-wrap"><div className="onto-lane-caption">{t("Parent purpose", "上级目的")}</div><button type="button" className="onto-focus-parent" onClick={() => setSelectedId(parent.id)} onDoubleClick={() => void enter(parent.id)}><span className="onto-file-icon" aria-hidden><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="2" /></svg></span>{parent.name}<small>{t("Enter", "进入")} ↗</small></button><div className="onto-hierarchy-line">↓</div></div>}
            <div className="onto-focus-row">
              <div className="onto-focus-side is-left"><button type="button" className="onto-purpose-pill is-serves" onClick={() => { setRelationType("serves"); setRelationOffset(0); setDrawer("relations"); }}>{t("Serves", "服务于")} <b>{relationCounts.serves}</b></button></div>
              <div className={`onto-focus-card${loading ? " is-loading" : ""}`}><span className="onto-focus-icon" aria-hidden><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="2" /></svg></span><div><strong>{focus.name}</strong><small>{t("Current goal", "当前目标")}</small></div><p>{focus.description || t("No description yet", "暂无描述")}</p><footer><span>{t("Subgoals", "子目标")} {childTotal}</span><span>{t("Relations", "关系")} {relationCounts.serves + relationCounts.advances + relationCounts.blocks}</span>{focus.progress != null && <span>{t("Progress", "进度")} {focus.progress}%</span>}</footer></div>
              <div className="onto-focus-side is-right"><button type="button" className="onto-purpose-pill is-advances" onClick={() => { setRelationType("advances"); setRelationOffset(0); setDrawer("relations"); }}>{t("Advances", "推进")} <b>{relationCounts.advances}</b></button><button type="button" className="onto-purpose-pill is-blocks" onClick={() => { setRelationType("blocks"); setRelationOffset(0); setDrawer("relations"); }}>{t("Blocks", "阻碍")} <b>{relationCounts.blocks}</b></button></div>
            </div>
            <div className="onto-hierarchy-line">↓</div><div className="onto-lane-caption">{t("Direct subgoals", "实现 / 直接下级目标")}</div>
            <div className="onto-child-grid">{children.map((goal) => <div key={goal.id} className={`onto-child-card${selectedId === goal.id ? " is-selected" : ""}`} onClick={() => setSelectedId(goal.id)} onDoubleClick={() => void enter(goal.id)}><strong><span className="onto-file-icon" aria-hidden><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="2" /></svg></span>{goal.name}</strong><p>{goal.description || ""}</p><footer>{t("Subgoals", "子目标")} {goal.child_count || 0}<button type="button" onClick={(event) => { event.stopPropagation(); void enter(goal.id); }}>{t("Enter", "进入")} ↗</button></footer></div>)}</div>
            {childTotal > children.length && <button type="button" className="onto-view-all" onClick={() => { setDrawerOffset(0); setDrawerQuery(""); setDrawer("children"); }}>＋ {t(`${childTotal - children.length} more subgoals · View all`, `还有 ${childTotal - children.length} 个子目标 · 查看全部`)}</button>}
          </>}
        </div> : <div className="onto-tree-overview"><div className="onto-lane-caption">{t("Current branch · expand goals on demand", "当前分支 · 按需展开目标")}</div>{roots.map((goal) => <button type="button" key={goal.id} onClick={() => void enter(goal.id)}>◎ {goal.name} <small>{goal.child_count || 0} {t("direct goals", "个直接目标")}</small></button>)}{rootTotal > roots.length && <button type="button" onClick={async () => { const result = await getGraphAnnotations(instance, datasetId, { parentId: "_roots", goalsLimit: PAGE, goalsOffset: roots.length }); setRoots((old) => [...old, ...result.goals]); }}>{t("More roots", "加载更多根目标")}</button>}</div>}
      </main>
      <div className={`onto-side-container onto-side-right${rightOpen ? "" : " is-collapsed"}`}><button type="button" className="onto-seam-tab onto-seam-tab-right" onClick={() => setRightOpen(!rightOpen)}>{rightOpen ? "›" : "‹"}</button>{rightOpen && <DetailPanel entity={selectedEntity} edges={relations.filter((edge) => edge.sourceId === selectedId || edge.targetId === selectedId)} focusId={focusId} language={language} path={selectedId === focusId ? path : undefined} onViewPath={() => void viewSelectedPath()} onSetFocus={(id) => void enter(id)} onSelectNeighbor={(id) => setSelectedId(id)} onCreateChild={createChild} onRelate={relateGoal} onCopy={copyGoal} onMove={moveGoal} onDelete={removeGoal} onEdit={editGoal} onExport={exportGoal} />}</div>
    </div>
    {drawer && <div className="onto-drawer-backdrop" onMouseDown={() => setDrawer(null)}><aside className="onto-drawer" onMouseDown={(event) => event.stopPropagation()}><header><strong>{drawer === "children" ? t("Browse subgoals", "浏览子目标") : drawer === "path" ? t("Goal path", "目标路径") : t("Purpose relations", "目的关系")}</strong><button type="button" onClick={() => setDrawer(null)}>×</button></header>
      {drawer === "children" && <><input value={drawerQuery} onChange={(event) => { setDrawerQuery(event.target.value); setDrawerOffset(0); }} placeholder={t("Search subgoals", "搜索子目标")} /><div className="onto-drawer-list">{drawerLoading ? t("Loading…", "加载中…") : drawerPage.map((goal) => <button type="button" key={goal.id} onClick={() => { setDrawer(null); void enter(goal.id); }}>◎ {goal.name}<small>{goal.child_count || 0} {t("subgoals", "个子目标")}</small></button>)}</div><footer><button type="button" disabled={drawerOffset === 0} onClick={() => setDrawerOffset(Math.max(0, drawerOffset - PAGE))}>{t("Previous", "上一页")}</button><span>{drawerOffset + 1}–{Math.min(drawerOffset + PAGE, drawerTotal)} / {drawerTotal}</span><button type="button" disabled={drawerOffset + PAGE >= drawerTotal} onClick={() => setDrawerOffset(drawerOffset + PAGE)}>{t("Next", "下一页")}</button></footer></>}
      {drawer === "path" && <div className="onto-drawer-list">{drawerPath.map((goal) => <button type="button" key={goal.id} onClick={() => { setDrawer(null); void enter(goal.id); }}>◎ {goal.name}</button>)}</div>}
      {drawer === "relations" && <><div className="onto-drawer-list">{drawerLoading ? t("Loading…", "加载中…") : relations.map((edge) => <button type="button" key={edge.id} onClick={() => { setSelectedId(edge.sourceId === focusId ? edge.targetId : edge.sourceId); setDrawer(null); }}>{edge.relationship} · {edge.sourceId === focusId ? edge.targetName : edge.sourceName}</button>)}</div><footer><button type="button" disabled={relationOffset === 0} onClick={() => setRelationOffset(Math.max(0, relationOffset - PAGE))}>{t("Previous", "上一页")}</button><span>{relationOffset + 1}–{Math.min(relationOffset + PAGE, relationTotal)} / {relationTotal}</span><button type="button" disabled={relationOffset + PAGE >= relationTotal} onClick={() => setRelationOffset(relationOffset + PAGE)}>{t("Next", "下一页")}</button></footer></>}
    </aside></div>}
  </div>;
}
