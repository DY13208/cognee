"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CogneeInstance } from "@/modules/instances/types";
import { analyzePurpose, createGraphAnnotation, createWorkspaceGoal, deleteWorkspaceGoal, getGoalDetail, getGoalModel, getGoalPath, getGoalRelations, getGraphAnnotations, getPurposeContext, getLatestOpenGoalProposal, moveWorkspaceGoal, reviewGoalCandidate, syncTeleologyFromCompanyTree, syncTeleologyGoals, updateWorkspaceGoal, type GoalModelView, type GraphAnnotation, type GraphNodeSummary, type ProposalItem, type TeleologyProposal } from "@/modules/teleology/teleologyApi";
import { buildDerivedGoalTree, parseDataNodeId, type DerivedGoalTree } from "./derivedGoalTree";
import { notifications } from "@mantine/notifications";
import NavPanel, { type GoalPage } from "./NavPanel";
import OntologyCanvas from "./OntologyCanvas";
import GoalFocusDetail from "./GoalFocusDetail";
import { buildPurposeNeighborhood } from "./purposeCanvas";
import PurposeReview from "./PurposeReview";
import AppDialog from "./AppDialog";
import SideRail from "./SideRail";
import { useSideOpen } from "./useSideOpen";
import { displayName } from "./entityMeta";
import type { OntologyEdge, OntologyEntity } from "./types";
import "./ontology.css";

type DatasetOpt = { id: string; name: string };
type GoalRelation = "serves" | "advances" | "blocks";
type GoalDialog =
  | { mode: "create"; parentId: string; name: string }
  | { mode: "relate"; sourceId: string; targetId: string; relationship: GoalRelation }
  | { mode: "edit"; id: string; name: string }
  | { mode: "move"; id: string; parentId: string }
  | { mode: "delete"; id: string }
  | { mode: "export"; id: string };
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
  const [pendingId, setPendingId] = useState<string | null>(null);
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
  const [relationType] = useState<"serves" | "advances" | "blocks" | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<"children" | "path" | "relations" | null>(null);
  const [drawerPath, setDrawerPath] = useState<GraphNodeSummary[]>([]);
  const [drawerQuery, setDrawerQuery] = useState("");
  const [drawerPage, setDrawerPage] = useState<GraphNodeSummary[]>([]);
  const [drawerTotal, setDrawerTotal] = useState(0);
  const [drawerOffset, setDrawerOffset] = useState(0);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const { leftOpen, rightOpen, setLeftOpen, setRightOpen } = useSideOpen();
  const [dialog, setDialog] = useState<GoalDialog | null>(null);
  const [topOpen, setTopOpen] = useState(true);
  const [datasetMenu, setDatasetMenu] = useState(false);
  const [why, setWhy] = useState<GraphNodeSummary[]>([]);
  const [constraints, setConstraints] = useState<GraphNodeSummary[]>([]);
  const [proposal, setProposal] = useState<TeleologyProposal | null>(null);
  const [selectedProposalItem, setSelectedProposalItem] = useState<ProposalItem | null>(null);
  const [navStatuses, setNavStatuses] = useState<Record<string, string>>({});
  const [goalModel, setGoalModel] = useState<GoalModelView | null>(null);
  const [reviewingGoal, setReviewingGoal] = useState(false);
  const [review, setReview] = useState<TeleologyProposal | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const hiddenRels = useMemo(() => new Set<string>(), []);
  const requestId = useRef(0);
  const derivedRef = useRef<DerivedGoalTree | null>(null);

  const loadPath = useCallback((goal: GraphNodeSummary) => getGoalPath(instance, datasetId, goal.id), [instance, datasetId]);

  const enter = useCallback(async (id: string, preview?: GraphNodeSummary) => {
    if (!datasetId) return;
    const dataNode = parseDataNodeId(id);
    const goalId = dataNode && derivedRef.current?.byId.get(dataNode.goalId)?.source === "derived_goal" ? dataNode.goalId : id;
    const derived = derivedRef.current?.byId.get(goalId)?.source === "derived_goal" ? derivedRef.current?.focus(goalId) : null;
    if (derived && derivedRef.current) {
      const serial = ++requestId.current;
      setLoading(false); setError(null); setPendingId(null);
      setFocusId(goalId); setSelectedId(dataNode ? id : goalId); setFocusGoal(derived.goal); setParent(null);
      setPath(derivedRef.current.path(goalId));
      setChildren(derived.children); setChildTotal(derived.children.length);
      setWhy(derived.purposes); setConstraints(derived.constraints); setProposal(null); setSelectedProposalItem(null);
      setRelations(derived.relations);
      setRelationCounts({ serves: derived.relations.length, advances: 0, blocks: 0 });
      setRelationTotal(derived.relations.length); setRelationOffset(0);
      if (serial !== requestId.current) return;
      return;
    }
    const serial = ++requestId.current;
    setLoading(true); setError(null); setPendingId(id);
    let relationPage: Awaited<ReturnType<typeof getGoalRelations>> | null = null;
    let childPage: Awaited<ReturnType<typeof getGraphAnnotations>> | null = null;
    try {
      // Relations and direct children are the canvas. Purpose context walks
      // every ancestor, so it starts only after this neighborhood is on screen.
      [relationPage, childPage] = await Promise.all([
        getGoalRelations(instance, datasetId, id, { limit: 30 }),
        getGraphAnnotations(instance, datasetId, { parentId: id, goalsLimit: CANVAS_PAGE }),
      ]);
    } catch (cause) {
      if (serial !== requestId.current) return;
      setError(cause instanceof Error ? cause.message : String(cause));
    }
    if (serial !== requestId.current) return;
    const named = relationPage?.items.find((edge) => edge.source_id === id || edge.target_id === id);
    const nextFocus: GraphNodeSummary = preview || {
      id,
      name: named ? (named.source_id === id ? named.source_name : named.target_name) : id,
      type: "Goal",
      description: "",
    };
    const visibleChildren = (childPage?.goals || []).slice(0, (childPage?.goals_total || 0) > 16 ? 12 : 16);
    setFocusId(id); setSelectedId(id); setFocusGoal(nextFocus); setParent(null);
    setPath([nextFocus]);
    setChildren(visibleChildren); setChildTotal(childPage?.goals_total ?? visibleChildren.length);
    setWhy([]); setConstraints([]); setProposal(null); setSelectedProposalItem(null);
    setRelations(relationPage ? edges(relationPage.items) : []);
    setRelationCounts(relationPage?.counts || { serves: 0, advances: 0, blocks: 0 });
    setRelationTotal(relationPage?.total || 0);
    const loadedChildren = childPage;
    if (loadedChildren) {
      setPages((old) => {
        const incoming = loadedChildren.goals;
        const prior = old[id];
        if (!prior?.loaded) {
          return { ...old, [id]: { items: incoming, total: loadedChildren.goals_total ?? incoming.length, loading: false, loaded: true, nextOffset: incoming.length } };
        }
        const items = [...prior.items];
        incoming.forEach((goal) => { if (!items.some((item) => item.id === goal.id)) items.push(goal); });
        return { ...old, [id]: { ...prior, items, loading: false, loaded: true } };
      });
    }
    setPendingId(null); setLoading(false);

    void getLatestOpenGoalProposal(instance, datasetId, id)
      .then((loaded) => { if (serial === requestId.current) setProposal(loaded); })
      .catch((cause) => { if (serial === requestId.current) setError(cause instanceof Error ? cause.message : String(cause)); });
    void getPurposeContext(instance, datasetId, id)
      .then((context) => {
        if (serial !== requestId.current) return;
        setWhy(context.purposes || []);
        setConstraints(context.constraints || []);
        if (context.goal) setFocusGoal(context.goal);
        const ancestors = context.ancestors || [];
        setParent(ancestors.length ? ancestors[ancestors.length - 1] : null);
        if (ancestors.length) setPath([...ancestors, context.goal]);
      })
      .catch((cause) => { if (serial === requestId.current) setError(cause instanceof Error ? cause.message : String(cause)); });
  }, [instance, datasetId]);

  const loadRoots = useCallback(async () => {
    if (!datasetId) return;
    setLoading(true); setError(null);
    try {
      const model = await getGoalModel(instance, datasetId);
      const tree = buildDerivedGoalTree(model, language);
      derivedRef.current = tree;
      setGoalModel(model);
      setRoots(tree.roots); setPages(tree.pages); setNavStatuses(tree.statuses); setRootTotal(tree.roots.length);
      if (tree.roots.length) await enter(tree.roots[0].id, tree.roots[0]);
      else setLoading(false);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); setLoading(false); }
  }, [instance, datasetId, enter, language]);

  useEffect(() => {
    requestId.current += 1; derivedRef.current = null; setGoalModel(null); setPendingId(null); setRoots([]); setPages({}); setFocusId(null); setSelectedId(null); setFocusGoal(null); setParent(null); setPath([]); setChildren([]); setRelations([]); setWhy([]); setConstraints([]); setProposal(null); setSelectedProposalItem(null); setReview(null);
    if (datasetId) void loadRoots();
  }, [datasetId, loadRoots]);

  useEffect(() => {
    if (!focusId || derivedRef.current?.byId.get(focusId)?.source === "derived_goal") return;
    const confirmed = why.length + constraints.length + relations.length;
    const candidateCount = proposal?.items.filter((item) => item.status !== "ignored" && item.kind !== "gap").length || 0;
    const confirmedLabel = confirmed ? language === "zh" ? `已确认 ${confirmed}` : `Confirmed ${confirmed}` : "";
    const candidateLabel = candidateCount ? language === "zh" ? `AI建议 ${candidateCount}` : `AI suggestions ${candidateCount}` : "";
    const label = [confirmedLabel, candidateLabel].filter(Boolean).join(" · ") || (proposal ? language === "zh" ? "无充分证据" : "Insufficient evidence" : null);
    if (label) setNavStatuses((old) => ({ ...old, [focusId]: label }));
  }, [focusId, why, constraints, relations, proposal, language]);

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
    return derivedRef.current?.search(query) || [];
  }, []);

  useEffect(() => {
    if (drawer !== "children" || !focusId || derivedRef.current?.byId.get(focusId)?.source === "derived_goal") return;
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
    if (drawer !== "relations" || !focusId || derivedRef.current?.byId.get(focusId)?.source === "derived_goal") return;
    let active = true;
    setDrawerLoading(true);
    void getGoalRelations(instance, datasetId, focusId, { relationship: relationType, offset: relationOffset, limit: PAGE }).then((result) => {
      if (!active) return;
      setRelations(edges(result.items)); setRelationCounts(result.counts); setRelationTotal(result.total);
    }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : String(cause)); }).finally(() => { if (active) setDrawerLoading(false); });
    return () => { active = false; };
  }, [drawer, focusId, relationOffset, relationType, instance, datasetId]);

  const neighborhood = useMemo(() => {
    if (!focus) return { entities: [], edges: [] };
    return buildPurposeNeighborhood({ focus, parent, purposes: why, constraints, relations, proposal, children });
  }, [focus, parent, why, constraints, relations, proposal, children]);

  const focusPreset = useMemo(() => (
    focus ? { goal: focus, purposes: why, constraints, relations, counts: relationCounts, proposal, children, childTotal } : null
  ), [focus, why, constraints, relations, relationCounts, proposal, children, childTotal]);

  const detailGoalId = useMemo(() => {
    if (!selectedId || !focus) return null;
    if (proposal?.items.some((item) => item.id === selectedId)) return focus.id;
    if (why.some((item) => item.id === selectedId) || constraints.some((item) => item.id === selectedId)) return focus.id;
    return selectedId;
  }, [selectedId, focus, proposal, why, constraints]);

  const selectedCandidate = goalModel?.candidates.find((candidate) => candidate.id === detailGoalId) || null;

  const selectedEntity = useMemo(() => {
    const found = [focus, parent, ...why, ...children, ...path, ...roots].find((goal) => goal?.id === selectedId);
    if (found) return entity(found);
    const relation = relations.find((edge) => edge.sourceId === selectedId || edge.targetId === selectedId);
    if (!relation || !selectedId) return null;
    return { id: selectedId, name: relation.sourceId === selectedId ? relation.sourceName : relation.targetName, type: "Goal", kind: "Goal" as const };
  }, [focus, parent, why, children, path, roots, selectedId, relations]);

  async function viewSelectedPath(id = selectedId) {
    try {
      let goal = [focus, parent, ...children, ...path, ...roots].find((item) => item?.id === id);
      if (!goal && id) {
        goal = await getGoalDetail(instance, datasetId, id);
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

  async function reviewSelectedGoal(status: "confirmed" | "rejected") {
    if (!selectedCandidate || reviewingGoal) return;
    const candidateId = selectedCandidate.id;
    const parentId = selectedCandidate.parent_candidate_id;
    setReviewingGoal(true);
    try {
      await reviewGoalCandidate(instance, datasetId, candidateId, status);
      const model = await getGoalModel(instance, datasetId);
      const tree = buildDerivedGoalTree(model, language);
      derivedRef.current = tree;
      setGoalModel(model);
      setRoots(tree.roots); setPages(tree.pages); setNavStatuses(tree.statuses); setRootTotal(tree.roots.length);
      const nextId = status === "rejected" ? (parentId && tree.byId.has(parentId) ? parentId : tree.roots[0]?.id) : candidateId;
      if (nextId) await enter(nextId);
      else { setFocusId(null); setSelectedId(null); setFocusGoal(null); setPath([]); setChildren([]); }
      notifications.show({ title: status === "confirmed" ? t("Goal confirmed", "目标已确认") : t("Goal rejected", "目标已驳回"), message: "", color: "green" });
    } catch (cause) {
      notifications.show({ title: t("Review failed", "审核失败"), message: cause instanceof Error ? cause.message : String(cause), color: "red" });
    } finally { setReviewingGoal(false); }
  }

  function createChild(id: string) {
    setDialog({ mode: "create", parentId: id, name: "" });
  }

  function relateGoal(id: string) {
    setDialog({ mode: "relate", sourceId: id, targetId: "", relationship: "serves" });
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
    const named = neighborhood.entities.find((item) => item.id === id);
    setDialog({ mode: "edit", id, name: named?.name || "" });
  }

  function moveGoal(id: string) {
    setDialog({ mode: "move", id, parentId: "" });
  }

  function removeGoal(id: string) {
    setDialog({ mode: "delete", id });
  }

  function exportGoal(id: string) {
    setDialog({ mode: "export", id });
  }

  function downloadGoal(id: string) {
    void Promise.all([getGoalDetail(instance, datasetId, id), getGoalRelations(instance, datasetId, id, { limit: 100 })]).then(([goal, purpose]) => {
      const blob = new Blob([JSON.stringify({ goal, purpose, relations_truncated: purpose.total > purpose.items.length }, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a"); link.href = url; link.download = `goal-${id}.json`; link.click();
      URL.revokeObjectURL(url);
    }).catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)));
  }

  function confirmDialog() {
    if (!dialog) return;
    if (dialog.mode === "create") {
      const name = dialog.name.trim();
      if (!name) return;
      const parentId = dialog.parentId;
      setDialog(null);
      void runGoalAction(async () => {
        const created = await createWorkspaceGoal(instance, datasetId, { parentId, name });
        return created.id;
      });
      return;
    }
    if (dialog.mode === "relate") {
      const targetId = dialog.targetId.trim();
      const relationship = dialog.relationship;
      if (!targetId) return;
      const sourceId = dialog.sourceId;
      setDialog(null);
      void runGoalAction(async () => { await createGraphAnnotation(instance, { datasetId, sourceId, targetId, relationship }); });
      return;
    }
    if (dialog.mode === "edit") {
      const name = dialog.name.trim();
      if (!name) return;
      const id = dialog.id;
      setDialog(null);
      void runGoalAction(async () => { await updateWorkspaceGoal(instance, datasetId, id, { name }); });
      return;
    }
    if (dialog.mode === "move") {
      const parentId = dialog.parentId.trim();
      if (!parentId) return;
      const id = dialog.id;
      setDialog(null);
      void runGoalAction(async () => { await moveWorkspaceGoal(instance, datasetId, id, parentId); }, id);
      return;
    }
    if (dialog.mode === "delete") {
      const id = dialog.id;
      const nextId = id === focusId ? parent?.id : focusId || undefined;
      setDialog(null);
      void runGoalAction(async () => { await deleteWorkspaceGoal(instance, datasetId, id); }, nextId);
      return;
    }
    const id = dialog.id;
    setDialog(null);
    downloadGoal(id);
  }

  async function analyzeCurrentGoal() {
    if (!focusId) return;
    setAnalyzing(true);
    onBusy(true);
    try {
      const result = await analyzePurpose(instance, datasetId, focusId);
      setProposal(result); setReview(result);
    } catch (cause) {
      notifications.show({ title: t("Analysis failed", "分析失败"), message: cause instanceof Error ? cause.message : String(cause), color: "red" });
    } finally { setAnalyzing(false); onBusy(false); }
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

  const dialogTitle = !dialog ? ""
    : dialog.mode === "create" ? t("New subgoal", "新建子目标")
    : dialog.mode === "relate" ? t("Link goal", "关联目标")
    : dialog.mode === "edit" ? t("Edit goal", "编辑目标")
    : dialog.mode === "move" ? t("Move goal", "移动目标")
    : dialog.mode === "delete" ? t("Delete this goal?", "确定删除此目标？")
    : t("Export this goal?", "导出此目标？");
  const dialogDescription = !dialog ? undefined
    : dialog.mode === "delete" ? t("This removes the goal from the workspace.", "将从工作区删除此目标。")
    : dialog.mode === "export" ? t("Downloads a JSON file for the selected goal.", "下载所选目标的 JSON 文件。")
    : undefined;

  return <div className="onto-root">
    <header className={`onto-top${topOpen ? "" : " is-collapsed"}`}>
      {topOpen ? <>
        <div style={{ position: "relative" }}><button type="button" className="onto-select" onClick={() => setDatasetMenu(!datasetMenu)}>{selectedDataset?.name || datasets[0]?.name || t("No dataset", "暂无数据集")} ▾</button>
          {datasetMenu && <div className="onto-search-menu">{datasets.map((dataset) => <button type="button" className="onto-search-item" key={dataset.id} onClick={() => { onSelectDataset(dataset); setDatasetMenu(false); }}>{dataset.name}</button>)}</div>}
        </div>
        <button type="button" className="onto-btn" disabled={busy || !datasetId} onClick={() => void syncTree()}>{t("Sync company tree", "同步公司树")}</button>
        <button type="button" className="onto-btn onto-btn-primary" title={t("Analyze this goal only. The result stays a proposal until you confirm.", "只分析当前目标。确认前都是候选。")} disabled={!focusId || busy || analyzing} onClick={() => void analyzeCurrentGoal()}>{analyzing ? t("Analyzing…", "分析中…") : t("Analyze purpose relations", "分析目的关系")}</button>
        <button type="button" className="onto-btn" disabled={busy || !datasetId} onClick={() => void syncYaml()}>{t("Sync YAML", "同步 YAML")}</button>
      </> : <span className="onto-collapsed-title">{t("Teleology", "目的论")} · {selectedDataset?.name || datasets[0]?.name}</span>}
      <button type="button" className="onto-btn onto-collapse-btn" onClick={() => { setTopOpen(!topOpen); onHeaderCollapsedChange?.(topOpen); }}>{topOpen ? t("Collapse ↑", "收起 ↑") : t("Expand ↓", "展开 ↓")}</button>
    </header>
    <div className="onto-body">
      <SideRail side="left" open={leftOpen} onOpen={() => setLeftOpen(true)} expandLabel={t("Expand goal tree", "展开目标目录")}>
        <NavPanel language={language} roots={roots} pages={pages} focusId={pendingId || focusId} pathIds={path.map((goal) => goal.id)} loading={loading} statuses={navStatuses} emptyLabel={t("No derived goals yet. The company tree stays as data and is not listed as goals.", "还没有派生目标。公司树留在数据层，不会被列成目标。")} onPick={(id, goal) => void enter(id, goal)} onExpand={expand} onSearch={search} onClose={() => setLeftOpen(false)} hasMoreRoots={rootTotal > roots.length} onLoadMoreRoots={() => { void getGraphAnnotations(instance, datasetId, { parentId: "_roots", goalsLimit: PAGE, goalsOffset: roots.length }).then((result) => setRoots((old) => [...old, ...result.goals])); }} />
      </SideRail>
      <main className="onto-main onto-focus-main">
        {error && <div className="onto-focus-error" role="alert">{error}</div>}
        <div className="onto-breadcrumb">{path.map((goal, index) => <span key={goal.id}><button type="button" onClick={() => void enter(goal.id)}>{goal.name}</button>{index < path.length - 1 && <b>›</b>}</span>)}</div>
        <OntologyCanvas
          focusId={focus?.id || null}
          entities={neighborhood.entities}
          edges={neighborhood.edges}
          selectedId={selectedId}
          viewMode="relation"
          hopDepth={2}
          relatedOnly={false}
          hiddenRels={hiddenRels}
          hoverId={hoverId}
          language={language}
          loading={loading}
          zoom={zoom}
          onSelect={(id) => {
            setSelectedId(id);
            if (!id) return;
            setRightOpen(true);
            setSelectedProposalItem(proposal?.items.find((item) => item.id === id) || null);
          }}
          onSetFocus={(id) => void enter(id)}
          onExpand={(id) => void enter(id)}
          onCanvasClick={() => { setSelectedId(null); setSelectedProposalItem(null); }}
          onHover={setHoverId}
        />
        <div className="onto-canvas-toolbar">
          <div className="onto-zoom-group">
            <button type="button" onClick={() => setZoom((value) => Math.max(0.5, Math.round((value - 0.1) * 10) / 10))}>−</button>
            <button type="button" onClick={() => setZoom(1)}>{Math.round(zoom * 100)}%</button>
            <button type="button" onClick={() => setZoom((value) => Math.min(1.8, Math.round((value + 0.1) * 10) / 10))}>+</button>
          </div>
        </div>
      </main>
      <SideRail side="right" open={rightOpen} onOpen={() => setRightOpen(true)} expandLabel={t("Expand details", "展开目标详情")}>
        <aside className="onto-detail teleology-node-detail">
          <div className="onto-detail-head">
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="onto-detail-kind">{t("Node detail", "节点详情")}</div>
              <div className="onto-detail-title">{selectedEntity?.name || focus?.name || t("Purpose", "目的")}</div>
            </div>
            <button type="button" className="onto-panel-close" onClick={() => setRightOpen(false)} aria-label={t("Collapse details", "收起目标详情")}>×</button>
          </div>
          {pendingId && pendingId !== focusId ? <div className="onto-detail-empty">{t("Loading confirmed relations…", "正在载入已确认关系…")}</div> : detailGoalId && focus ? <>
            {selectedCandidate && <section className="teleology-goal-review" aria-label={t("Review AI goal", "审核 AI 目标")}>
              <div className="teleology-goal-review-status">{selectedCandidate.status === "confirmed" ? t("Confirmed goal", "目标已确认") : t("Goal awaiting confirmation", "目标待确认")}</div>
              {selectedCandidate.reason && <p><strong>{t("Reason", "生成理由")}</strong>{selectedCandidate.reason}</p>}
              {selectedCandidate.evidence.length > 0 && <div><strong>{t("Evidence", "来源证据")}</strong><ul>{selectedCandidate.evidence.map((entry) => <li key={entry.node_id}>{entry.name}{entry.text ? ` · ${entry.text}` : ""}</li>)}</ul></div>}
              <div className="teleology-goal-review-actions">
                {selectedCandidate.status !== "confirmed" && <button type="button" disabled={reviewingGoal} onClick={() => void reviewSelectedGoal("confirmed")}>{reviewingGoal ? t("Saving…", "保存中…") : t("Confirm goal", "确认目标")}</button>}
                <button type="button" disabled={reviewingGoal} onClick={() => void reviewSelectedGoal("rejected")}>{t("Reject goal", "驳回目标")}</button>
              </div>
              <small>{t("Review changes the derived goal only. It does not edit the company tree or commit purpose relations.", "审核只改变派生目标状态，不修改公司树，也不提交目的关系。")}</small>
            </section>}
            <div className="teleology-detail-actions">
              <button type="button" disabled={detailGoalId === focusId} onClick={() => void enter(detailGoalId)}>{t("Set as center", "设为中心")}</button>
              <button type="button" onClick={() => relateGoal(detailGoalId)}>{t("Link", "关联")}</button>
              <button type="button" onClick={() => editGoal(detailGoalId)}>{t("Edit", "编辑")}</button>
              <button type="button" onClick={() => createChild(detailGoalId)}>{t("Subgoal", "子目标")}</button>
              <button type="button" onClick={() => void viewSelectedPath(detailGoalId)}>{t("Path", "路径")}</button>
              <button type="button" onClick={() => copyGoal(detailGoalId)}>{t("Copy", "复制")}</button>
              <button type="button" onClick={() => moveGoal(detailGoalId)}>{t("Move", "移动")}</button>
              <button type="button" onClick={() => exportGoal(detailGoalId)}>{t("Export", "导出")}</button>
              <button type="button" onClick={() => removeGoal(detailGoalId)}>{t("Delete", "删除")}</button>
            </div>
            <GoalFocusDetail
              instance={instance}
              datasetId={datasetId}
              goalId={detailGoalId}
              preset={detailGoalId === focus.id ? focusPreset : null}
              language={language}
              selectedProposalItem={selectedProposalItem}
              onSelectProposal={(item) => { setSelectedProposalItem(item); setSelectedId(item.id); }}
              onSelectGoal={(id) => void enter(id)}
              onAnalyze={detailGoalId === focus.id ? () => void analyzeCurrentGoal() : undefined}
              onReviewProposal={(next) => setReview(next)}
              onShowChildren={detailGoalId === focus.id ? () => { setDrawerOffset(0); setDrawerQuery(""); setDrawer("children"); } : undefined}
            />
          </> : <div className="onto-detail-empty">{t("Click a node on the canvas to inspect its purpose.", "在画布上点一个节点，查看它的目的。")}</div>}
        </aside>
        <div className="teleology-detail-legend" aria-label={t("Relation legend", "关系图例")}>
          <i />{t("Confirmed", "已确认")}
          <i className="is-proposed" />{t("AI suggestion", "AI建议")}
          <span>WHY · Purpose · Constraint</span>
        </div>
      </SideRail>
    </div>
    {review && <PurposeReview instance={instance} datasetId={datasetId} proposal={review} language={language} onClose={() => setReview(null)} onCommitted={() => { setReview(null); if (focusId) void enter(focusId); }} />}
    {drawer && <div className="onto-drawer-backdrop" onMouseDown={() => setDrawer(null)}><aside className="onto-drawer" onMouseDown={(event) => event.stopPropagation()}><header><strong>{drawer === "children" ? t("Browse subgoals", "浏览子目标") : drawer === "path" ? t("Goal path", "目标路径") : t("Purpose relations", "目的关系")}</strong><button type="button" onClick={() => setDrawer(null)}>×</button></header>
      {drawer === "children" && <><input value={drawerQuery} onChange={(event) => { setDrawerQuery(event.target.value); setDrawerOffset(0); }} placeholder={t("Search subgoals", "搜索子目标")} /><div className="onto-drawer-list">{drawerLoading ? t("Loading…", "加载中…") : drawerPage.map((goal) => <button type="button" key={goal.id} onClick={() => { setDrawer(null); void enter(goal.id); }}>◎ {goal.name}<small>{goal.child_count || 0} {t("subgoals", "个子目标")}</small></button>)}</div><footer><button type="button" disabled={drawerOffset === 0} onClick={() => setDrawerOffset(Math.max(0, drawerOffset - PAGE))}>{t("Previous", "上一页")}</button><span>{drawerOffset + 1}–{Math.min(drawerOffset + PAGE, drawerTotal)} / {drawerTotal}</span><button type="button" disabled={drawerOffset + PAGE >= drawerTotal} onClick={() => setDrawerOffset(drawerOffset + PAGE)}>{t("Next", "下一页")}</button></footer></>}
      {drawer === "path" && <div className="onto-drawer-list">{drawerPath.map((goal) => <button type="button" key={goal.id} onClick={() => { setDrawer(null); void enter(goal.id); }}>◎ {goal.name}</button>)}</div>}
      {drawer === "relations" && <><div className="onto-drawer-list">{drawerLoading ? t("Loading…", "加载中…") : relations.map((edge) => <button type="button" key={edge.id} onClick={() => { setSelectedId(edge.sourceId === focusId ? edge.targetId : edge.sourceId); setDrawer(null); }}>{edge.relationship} · {edge.sourceId === focusId ? edge.targetName : edge.sourceName}</button>)}</div><footer><button type="button" disabled={relationOffset === 0} onClick={() => setRelationOffset(Math.max(0, relationOffset - PAGE))}>{t("Previous", "上一页")}</button><span>{relationOffset + 1}–{Math.min(relationOffset + PAGE, relationTotal)} / {relationTotal}</span><button type="button" disabled={relationOffset + PAGE >= relationTotal} onClick={() => setRelationOffset(relationOffset + PAGE)}>{t("Next", "下一页")}</button></footer></>}
    </aside></div>}
    <AppDialog
      opened={dialog !== null}
      title={dialogTitle}
      description={dialogDescription}
      confirmLabel={dialog?.mode === "delete" ? t("Delete", "删除") : dialog?.mode === "export" ? t("Export", "导出") : t("Confirm", "确认")}
      cancelLabel={t("Cancel", "取消")}
      danger={dialog?.mode === "delete"}
      onCancel={() => setDialog(null)}
      onConfirm={confirmDialog}
    >
      {dialog?.mode === "create" || dialog?.mode === "edit" ? (
        <label>
          {t("Name", "名称")}
          <input className="onto-input" value={dialog.name} onChange={(event) => setDialog({ ...dialog, name: event.target.value })} onKeyDown={(event) => { if (event.key === "Enter") confirmDialog(); }} />
        </label>
      ) : null}
      {dialog?.mode === "relate" ? (
        <>
          <label>
            {t("Related goal ID", "关联目标 ID")}
            <input className="onto-input" value={dialog.targetId} onChange={(event) => setDialog({ ...dialog, targetId: event.target.value })} />
          </label>
          <label>
            {t("Relationship", "关系类型")}
            <select className="onto-select" value={dialog.relationship} onChange={(event) => setDialog({ ...dialog, relationship: event.target.value as GoalRelation })}>
              <option value="serves">serves</option>
              <option value="advances">advances</option>
              <option value="blocks">blocks</option>
            </select>
          </label>
        </>
      ) : null}
      {dialog?.mode === "move" ? (
        <label>
          {t("New parent goal ID", "新上级目标 ID")}
          <input className="onto-input" value={dialog.parentId} onChange={(event) => setDialog({ ...dialog, parentId: event.target.value })} onKeyDown={(event) => { if (event.key === "Enter") confirmDialog(); }} />
        </label>
      ) : null}
    </AppDialog>
  </div>;
}
