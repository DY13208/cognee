"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useCogniInstance } from "@/modules/tenant/TenantProvider";
import CoveragePanel from "./CoveragePanel";
import { TrackPageView } from "@/modules/analytics";
import { useFilter } from "@/ui/layout/FilterContext";
import recallKnowledge from "@/modules/datasets/recallKnowledge";
import {
  getTeleology,
  createTeleologyNode,
  updateTeleologyNode,
  deleteTeleologyNode,
  loadSampleTeleology,
  clearTeleology,
  getGraphAnnotations,
  analyzePurpose,
  getGoalRelations,
  getPurposeContext,
  getLatestOpenGoalProposal,
  getGoalPath,
  getGoalModel,
  syncTeleologyGoals,
  syncTeleologyFromCompanyTree,
  createGraphAnnotation,
  deleteGraphAnnotation,
  type TeleologyStatus,
  type TeleologyNode,
  type TeleologyNodeInput,
  type TeleologyNodeType,
  type TeleologyRelationship,
  type GraphAnnotationsPayload,
  type GraphAnnotation,
  type GraphNodeSummary,
  type PurposeContext,
  type TeleologyProposal,
} from "@/modules/teleology/teleologyApi";
import PageLoading from "@/ui/elements/PageLoading";
import DeleteConfirmModal from "@/ui/elements/DeleteConfirmModal";
import TeleologyNodeModal from "./TeleologyNodeModal";
import PurposeLensGraph, {
  REL_COLOR,
  relationshipColor,
  type PurposeGraphLink,
  type PurposeGraphNode,
} from "./PurposeLensGraph";
import { notifications } from "@mantine/notifications";
import { t, useBusinessLanguage } from "@/modules/business/BusinessLanguageContext";
import GoalNav, { type GoalPage } from "./browser/NavPanel";
import { buildDerivedGoalTree, parseDataNodeId, type DerivedGoalTree } from "./browser/derivedGoalTree";
import GoalFocusDetail from "./browser/GoalFocusDetail";
import { shouldShowFocusDetail } from "./browser/TeleologyFocusMap";
import PurposeReview from "./browser/PurposeReview";
import type { OntologyEdge } from "./browser/types";
import SideRail from "./browser/SideRail";
import { useSideOpen } from "./browser/useSideOpen";
import "./browser/ontology.css";

const REL_ZH: Record<TeleologyRelationship, string> = {
  serves: "服务于",
  advances: "推进",
  blocks: "阻碍",
};

/** Mind-map titles often arrive as HTML / entities — clean for UI labels. */
function displayName(raw: string, fallback = ""): string {
  let s = String(raw || "");
  for (let i = 0; i < 3; i += 1) {
    const next = s
      .replace(/&amp;/gi, "&")
      .replace(/&lt;/gi, "<")
      .replace(/&gt;/gi, ">")
      .replace(/&quot;/gi, '"')
      .replace(/&#39;/gi, "'")
      .replace(/&nbsp;/gi, " ");
    if (next === s) break;
    s = next;
  }
  s = s.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
  return s || fallback || String(raw || "").trim();
}

const MAX_LENS_NODES = 64;

const selectStyle: CSSProperties = {
  background: "#1a1a1c",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 8,
  padding: "8px 12px",
  fontSize: 13,
  fontFamily: "inherit",
  color: "#EDECEA",
  outline: "none",
  width: "100%",
  // Native <option> menus follow the OS theme; without this, Windows often
  // paints a white popup while our text stays light → unreadable.
  colorScheme: "dark",
};

const optionStyle: CSSProperties = {
  background: "#1a1a1c",
  color: "#EDECEA",
};

const inputStyle: CSSProperties = { ...selectStyle };

function btn(primary = false): CSSProperties {
  return {
    background: primary ? "rgba(188,155,255,0.22)" : "rgba(255,255,255,0.06)",
    border: primary ? "1px solid rgba(188,155,255,0.45)" : "1px solid rgba(255,255,255,0.12)",
    borderRadius: 8,
    padding: "7px 12px",
    fontSize: 13,
    fontWeight: 600,
    color: "#EDECEA",
    cursor: "pointer",
    fontFamily: "inherit",
    whiteSpace: "nowrap",
  };
}

function Shell({ children }: { children: ReactNode }) {
  return <div className="onto-root">{children}</div>;
}

export default function TeleologyClassicPage() {
  const { language } = useBusinessLanguage();
  const { cogniInstance, isInitializing } = useCogniInstance();
  const { datasets, selectedDataset, setSelectedDataset, loading: datasetsLoading } = useFilter();
  const [actionsHost, setActionsHost] = useState<HTMLElement | null>(null);
  const [coverageOpen, setCoverageOpen] = useState(false);
  const { leftOpen, rightOpen, setLeftOpen, setRightOpen } = useSideOpen();

  useEffect(() => {
    setActionsHost(document.getElementById("teleology-classic-actions"));
  }, []);

  const [status, setStatus] = useState<TeleologyStatus | null>(null);
  const [graph, setGraph] = useState<GraphAnnotationsPayload | null>(null);
  const [brainNodes, setBrainNodes] = useState<{ id: string; name: string; type: string }[]>([]);
  const [navRoots, setNavRoots] = useState<GraphNodeSummary[]>([]);
  const [navPages, setNavPages] = useState<Record<string, GoalPage>>({});
  const [navPath, setNavPath] = useState<string[]>([]);
  const navPagesRef = useRef(navPages);
  navPagesRef.current = navPages;
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [datasetMenuOpen, setDatasetMenuOpen] = useState(false);
  const [lensGoalId, setLensGoalId] = useState("");
  const [focusContext, setFocusContext] = useState<PurposeContext | null>(null);
  const [focusRelations, setFocusRelations] = useState<OntologyEdge[]>([]);
  const [focusProposal, setFocusProposal] = useState<TeleologyProposal | null>(null);
  const [reviewProposal, setReviewProposal] = useState<TeleologyProposal | null>(null);
  const [focusRevision, setFocusRevision] = useState(0);
  const [classicNavStatuses, setClassicNavStatuses] = useState<Record<string, string>>({});
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [addRel, setAddRel] = useState<TeleologyRelationship>("serves");

  const [recallQuery, setRecallQuery] = useState("");
  const [recallMode, setRecallMode] = useState<"rerank" | "filter">("rerank");
  const [recallResult, setRecallResult] = useState("");
  const [showRecall, setShowRecall] = useState(false);

  const [vocabOpen, setVocabOpen] = useState(false);
  const [vocabQuery, setVocabQuery] = useState("");
  const [vocabHits, setVocabHits] = useState<GraphNodeSummary[]>([]);
  const [vocabTotal, setVocabTotal] = useState<number | null>(null);
  const [vocabLoading, setVocabLoading] = useState(false);
  const [vocabHasMore, setVocabHasMore] = useState(false);
  const vocabSeq = useRef(0);
  const [confirmClear, setConfirmClear] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<TeleologyNode | null>(null);
  const [deleteEdge, setDeleteEdge] = useState<GraphAnnotation | null>(null);
  const [editor, setEditor] = useState<{
    mode: "create" | "edit";
    node?: TeleologyNode;
    defaultType?: TeleologyNodeType;
  } | null>(null);

  const datasetId = selectedDataset?.id || datasets[0]?.id || "";
  const derivedTreeRef = useRef<DerivedGoalTree | null>(null);

  useEffect(() => {
    if (!cogniInstance || !datasetId || !lensGoalId) return;
    const tree = derivedTreeRef.current;
    if (tree?.byId.get(lensGoalId)?.source === "derived_goal") {
      const focus = tree.focus(lensGoalId);
      if (!focus) return;
      setFocusContext({
        dataset_id: datasetId,
        goal: focus.goal,
        ancestors: tree.path(lensGoalId).slice(0, -1),
        children: focus.children,
        children_total: focus.children.length,
        note: focus.goal.description,
        purposes: focus.purposes,
        constraints: focus.constraints,
        relations: [],
        entities: focus.children,
        documents: [],
        source: "ai_goal_model",
        revision: lensGoalId,
        missing_purpose: focus.purposes.length === 0,
      });
      setFocusRelations(focus.relations);
      setFocusProposal(null);
      setLoadError(null);
      return;
    }
    let active = true;
    setFocusContext(null); setFocusRelations([]); setFocusProposal(null);
    void getPurposeContext(cogniInstance, datasetId, lensGoalId)
      .then((context) => { if (active) setFocusContext(context); })
      .catch((cause) => { if (active) setLoadError(cause instanceof Error ? cause.message : String(cause)); });
    void getGoalRelations(cogniInstance, datasetId, lensGoalId, { limit: 100 })
      .then((result) => { if (active) setFocusRelations(result.items.map((edge) => ({ id: `${edge.source_id}|${edge.relationship}|${edge.target_id}`, sourceId: edge.source_id, targetId: edge.target_id, sourceName: edge.source_name, targetName: edge.target_name, sourceType: edge.source_type, targetType: edge.target_type, relationship: edge.relationship }))); })
      .catch((cause) => { if (active) setLoadError(cause instanceof Error ? cause.message : String(cause)); });
    void getLatestOpenGoalProposal(cogniInstance, datasetId, lensGoalId)
      .then((proposal) => { if (active) setFocusProposal(proposal); })
      .catch((cause) => { if (active) setLoadError(cause instanceof Error ? cause.message : String(cause)); });
    return () => { active = false; };
  }, [cogniInstance, datasetId, lensGoalId, focusRevision]);

  useEffect(() => {
    if (!cogniInstance || !datasetId) return;
    let active = true;
    setLoading(true);
    void getGoalModel(cogniInstance, datasetId)
      .then((model) => {
        if (!active) return;
        const tree = buildDerivedGoalTree(model, language === "zh" ? "zh" : "en");
        derivedTreeRef.current = tree;
        setNavRoots(tree.roots);
        setNavPages(tree.pages);
        setClassicNavStatuses(tree.statuses);
        const first = tree.roots[0];
        if (first) {
          setLensGoalId(first.id);
          setSelectedGoal(first);
          setNavPath(tree.pathIds(first.id));
        } else {
          setLensGoalId("");
          setSelectedGoal(null);
          setGraph(null);
        }
      })
      .catch((cause) => { if (active) setLoadError(cause instanceof Error ? cause.message : String(cause)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [cogniInstance, datasetId, language]);

  useEffect(() => {
    if (!lensGoalId) return;
    const confirmed = (focusContext?.purposes.length || 0) + (focusContext?.constraints.length || 0) + focusRelations.length;
    const candidates = focusProposal?.items.filter((item) => item.status !== "ignored" && item.kind !== "gap").length || 0;
    const confirmedLabel = confirmed ? t(language, `Confirmed ${confirmed}`, `已确认 ${confirmed}`) : "";
    const candidateLabel = candidates ? t(language, `AI suggestions ${candidates}`, `AI建议 ${candidates}`) : "";
    const label = [confirmedLabel, candidateLabel].filter(Boolean).join(" · ") || (focusProposal ? t(language, "Insufficient evidence", "无充分证据") : null);
    if (derivedTreeRef.current?.byId.get(lensGoalId)?.source === "derived_goal") return;
    if (label) setClassicNavStatuses((old) => ({ ...old, [lensGoalId]: label }));
  }, [lensGoalId, focusContext, focusRelations, focusProposal, language]);

  const [goalQuery, setGoalQuery] = useState("");
  const [goalHits, setGoalHits] = useState<GraphNodeSummary[]>([]);
  const [goalMenuOpen, setGoalMenuOpen] = useState(false);
  const [selectedGoal, setSelectedGoal] = useState<GraphNodeSummary | null>(null);
  const goalSearchSeq = useRef(0);

  const refresh = useCallback(async () => {
    if (!cogniInstance || !datasetId) {
      setGraph(null);
      setBrainNodes([]);
      setGoalHits([]);
      setSelectedGoal(null);
      setLoading(false);
      return;
    }
    setLoadError(null);
    try {
      // Roots only. Expanding a row loads its direct children; the canvas loads the focused goal.
      const yaml = await getTeleology(cogniInstance, { limit: 40 }).catch(() => null);
      if (yaml) setStatus(yaml);
      setBrainNodes([]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setLoadError(msg);
      setGraph(null);
    }
  }, [cogniInstance, datasetId]);

  const searchGoals = useCallback(
    async (query: string, opts?: { parentId?: string; mode?: "browse" | "search" }) => {
      if (!cogniInstance || !datasetId) return;
      const seq = ++goalSearchSeq.current;
      const trimmed = query.trim();
      const mode = opts?.mode ?? (trimmed ? "search" : "browse");
      try {
        const res = await getGraphAnnotations(cogniInstance, datasetId, {
          q: mode === "search" && trimmed ? trimmed : undefined,
          limit: 1,
          goalsLimit: 40,
          parentId: mode === "browse" ? opts?.parentId ?? "_roots" : undefined,
        });
        if (seq !== goalSearchSeq.current) return;
        setGoalHits(
          (res.goals || []).map((g) => ({
            ...g,
            name: displayName(g.name, g.id),
            description: displayName(g.description || ""),
            parent_name: g.parent_name ? displayName(g.parent_name) : g.parent_name,
          })),
        );
      } catch {
        if (seq !== goalSearchSeq.current) return;
        setGoalHits([]);
      } finally { /* completed */ }
    },
    [cogniInstance, datasetId],
  );

  const expandNav = useCallback(async (id: string, more = false) => {
    if (!cogniInstance || !datasetId) return;
    const prior = navPagesRef.current[id];
    if (prior?.loading || (!more && prior?.loaded)) return;
    const offset = more ? prior?.nextOffset || 0 : 0;
    setNavPages((old) => ({
      ...old,
      [id]: {
        items: old[id]?.items || [],
        total: old[id]?.total || 0,
        loaded: old[id]?.loaded,
        nextOffset: old[id]?.nextOffset || 0,
        loading: true,
      },
    }));
    try {
      const result = await getGraphAnnotations(cogniInstance, datasetId, {
        parentId: id,
        goalsLimit: 30,
        goalsOffset: offset,
        limit: 1,
      });
      setNavPages((old) => {
        const items = [...(old[id]?.items || []), ...(result.goals || [])];
        return {
          ...old,
          [id]: {
            items: items.filter((item, index) => items.findIndex((candidate) => candidate.id === item.id) === index),
            total: result.goals_total ?? offset + (result.goals?.length || 0),
            loading: false,
            loaded: true,
            nextOffset: offset + (result.goals?.length || 0),
          },
        };
      });
    } catch (cause) {
      setNavPages((old) => ({ ...old, [id]: { ...old[id], items: old[id]?.items || [], total: old[id]?.total || 0, loading: false } }));
      setLoadError(cause instanceof Error ? cause.message : String(cause));
    }
  }, [cogniInstance, datasetId]);

  const searchNav = useCallback(async (query: string) => {
    return derivedTreeRef.current?.search(query) || [];
  }, []);

  const pickNavGoal = useCallback(async (id: string) => {
    const data = parseDataNodeId(id);
    const goalId = data?.goalId || id;
    const tree = derivedTreeRef.current;
    const goal = tree?.byId.get(goalId);
    if (goal?.source === "derived_goal" && tree) {
      setLensGoalId(goalId);
      setSelectedNodeId(data ? id : goalId);
      setSelectedGoal(goal);
      setNavPath(tree.pathIds(goalId));
      return;
    }
    setLensGoalId(id);
    setSelectedNodeId(null);
    const known = [navRoots, ...Object.values(navPages).map((page) => page.items)].flat().find((item) => item.id === id);
    if (known) {
      setSelectedGoal({
        ...known,
        name: displayName(known.name, known.id),
        description: displayName(known.description || ""),
      });
    }
    if (!cogniInstance || !datasetId) return;
    try {
      const chain = await getGoalPath(cogniInstance, datasetId, id);
      setNavPath(chain.map((item) => item.id));
      const current = chain[chain.length - 1];
      if (current) {
        setSelectedGoal({
          ...current,
          name: displayName(current.name, current.id),
          description: displayName(current.description || ""),
        });
      }
    } catch {
      setNavPath([id]);
    }
  }, [cogniInstance, datasetId, navPages, navRoots]);

  useEffect(() => {
    if (!cogniInstance || isInitializing || datasetsLoading) return;
    if (!selectedDataset) {
      const preferred = datasets.find((dataset) => dataset.name.trim().toLowerCase() === "yiran_cpd");
      if (preferred || datasets[0]) setSelectedDataset(preferred ?? datasets[0]);
    }
  }, [cogniInstance, isInitializing, datasetsLoading, datasets, selectedDataset, setSelectedDataset]);

  useEffect(() => {
    if (!cogniInstance || isInitializing || !datasetId) return;
    setGoalQuery("");
    setGoalHits([]);
    refresh();
  }, [cogniInstance, isInitializing, datasetId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!cogniInstance || !datasetId || isInitializing) return;
    if (!lensGoalId || derivedTreeRef.current?.byId.get(lensGoalId)?.source === "derived_goal") {
      if (lensGoalId) setGraph(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const neighbourhood = await getGraphAnnotations(cogniInstance, datasetId, {
          limit: 80,
          goalsLimit: 40,
          goalId: lensGoalId,
        });
        if (!cancelled) setGraph(neighbourhood);
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [cogniInstance, datasetId, lensGoalId, isInitializing]);

  useEffect(() => {
    if (!goalMenuOpen || !cogniInstance || !datasetId) return;
    const handle = window.setTimeout(() => {
      const trimmed = goalQuery.trim();
      if (trimmed) {
        void searchGoals(trimmed, { mode: "search" });
      } else {
        void searchGoals("", { mode: "browse", parentId: "_roots" });
      }
    }, 220);
    return () => window.clearTimeout(handle);
  }, [goalQuery, goalMenuOpen, cogniInstance, datasetId, searchGoals]);

  const loadVocabPage = useCallback(
    async (query: string, offset: number, append: boolean) => {
      if (!cogniInstance || !datasetId) return;
      const seq = ++vocabSeq.current;
      setVocabLoading(true);
      try {
        const pageSize = 40;
        const res = await getGraphAnnotations(cogniInstance, datasetId, {
          q: query.trim() || undefined,
          limit: 1,
          goalsLimit: pageSize,
          goalsOffset: offset,
        });
        if (seq !== vocabSeq.current) return;
        const cleaned = (res.goals || []).map((g) => ({
          ...g,
          name: displayName(g.name, g.id),
          description: displayName(g.description || ""),
        }));
        setVocabHits((prev) => (append ? [...prev, ...cleaned] : cleaned));
        const total = res.goals_total ?? cleaned.length;
        setVocabTotal(total);
        setVocabHasMore(offset + cleaned.length < total && cleaned.length > 0);
      } catch {
        if (seq !== vocabSeq.current) return;
        if (!append) setVocabHits([]);
        setVocabHasMore(false);
      } finally {
        if (seq === vocabSeq.current) setVocabLoading(false);
      }
    },
    [cogniInstance, datasetId],
  );

  useEffect(() => {
    if (!vocabOpen || !cogniInstance || !datasetId) return;
    const handle = window.setTimeout(() => {
      void loadVocabPage(vocabQuery, 0, false);
    }, 280);
    return () => window.clearTimeout(handle);
  }, [vocabOpen, vocabQuery, cogniInstance, datasetId, loadVocabPage]);

  function pickGoal(goal: GraphNodeSummary | null) {
    if (!goal) {
      setLensGoalId("");
      setSelectedGoal(null);
      setGoalQuery("");
      setGoalMenuOpen(false);
      return;
    }
    const cleaned = {
      ...goal,
      name: displayName(goal.name, goal.id),
      description: displayName(goal.description || ""),
    };
    setSelectedGoal(cleaned);
    setLensGoalId(cleaned.id);
    setGoalQuery(cleaned.cpd_kind === "goal" ? `CPD · ${cleaned.name}` : cleaned.name);
    setGoalMenuOpen(false);
  }

  const annotations = useMemo(
    () =>
      (graph?.annotations ?? []).map((edge) => ({
        ...edge,
        source_name: displayName(edge.source_name, edge.source_id),
        target_name: displayName(edge.target_name, edge.target_id),
      })),
    [graph],
  );

  const purposeEdges = useMemo(() => {
    const key = (s: string, t: string, r: string) => `${s}|${t}|${r}`;
    const seen = new Set<string>();
    const out: GraphAnnotation[] = [];
    for (const edge of annotations) {
      if (edge.origin === "system_derived") continue;
      if (!["serves", "advances", "blocks"].includes(String(edge.relationship))) continue;
      const k = key(edge.source_id, edge.target_id, String(edge.relationship));
      if (seen.has(k)) continue;
      seen.add(k);
      out.push(edge);
    }
    return out;
  }, [annotations]);

  const linkedIdsForLens = useMemo(() => {
    if (!lensGoalId) return null;
    const ids = new Set<string>([lensGoalId]);
    for (const edge of purposeEdges) {
      if (edge.target_id === lensGoalId || edge.source_id === lensGoalId) {
        ids.add(edge.source_id);
        ids.add(edge.target_id);
      }
    }
    for (const edge of focusRelations) { ids.add(edge.sourceId); ids.add(edge.targetId); }
    for (const node of [...(focusContext?.purposes || []), ...(focusContext?.constraints || [])]) ids.add(node.id);
    for (const item of focusProposal?.items || []) {
      if (item.status === "ignored") continue;
      if (item.kind !== "relation") ids.add(item.id);
      if (item.kind === "relation") {
        if (item.source) ids.add(item.source);
        if (item.target) ids.add(item.target);
      }
    }
    return ids;
  }, [purposeEdges, lensGoalId, focusProposal, focusContext, focusRelations]);

  const lensGoals = useMemo((): GraphNodeSummary[] => {
    return (graph?.goals ?? []).map((g) => ({
      ...g,
      name: displayName(g.name, g.id),
      description: displayName(g.description || ""),
    }));
  }, [graph]);

  const graphNodes: PurposeGraphNode[] = useMemo(() => {
    const byId = new Map<string, PurposeGraphNode>();

    const add = (node: PurposeGraphNode) => {
      if (byId.has(node.id)) return;
      if (linkedIdsForLens && !linkedIdsForLens.has(node.id)) return;
      byId.set(node.id, node);
    };

    for (const child of focusContext?.entities || []) {
      add({ id: child.id, name: displayName(child.name, child.id), type: child.type || "Data", kind: "entity", dimmed: false });
    }

    const center = focusContext?.goal || selectedGoal;
    if (center) {
      add({
        id: center.id,
        name: displayName(center.name, center.id),
        type: center.type || "Goal",
        kind: "goal",
        dimmed: false,
        status: "confirmed",
      });
    }

    for (const g of lensGoals) {
      if (!linkedIdsForLens && purposeEdges.length > 0) {
        const onPurposeEdge = purposeEdges.some(
          (e) => e.source_id === g.id || e.target_id === g.id,
        );
        if (!onPurposeEdge) continue;
      }
      add({
        id: g.id,
        name: displayName(g.name, g.id),
        type: g.type || "Goal",
        kind: "goal",
        dimmed: false,
      });
    }

    for (const node of focusContext?.purposes || []) {
      add({ id: node.id, name: node.name, type: node.type || "Purpose", kind: "purpose", dimmed: false, status: "confirmed" });
    }
    for (const node of focusContext?.constraints || []) {
      add({ id: node.id, name: node.name, type: node.type || "Constraint", kind: "constraint", dimmed: false, status: "confirmed" });
    }

    for (const edge of purposeEdges) {
      if (linkedIdsForLens) {
        const touches =
          linkedIdsForLens.has(edge.source_id) && linkedIdsForLens.has(edge.target_id);
        if (!touches) continue;
      }
      add({
        id: edge.source_id,
        name: displayName(edge.source_name, edge.source_id),
        type: edge.source_type,
        kind: edge.source_type === "Purpose" ? "purpose" : edge.source_type === "Constraint" ? "constraint" : ["Goal", "Purpose", "Constraint"].includes(edge.source_type) ? "goal" : "entity",
        dimmed: false,
      });
      add({
        id: edge.target_id,
        name: displayName(edge.target_name, edge.target_id),
        type: edge.target_type,
        kind: edge.target_type === "Purpose" ? "purpose" : edge.target_type === "Constraint" ? "constraint" : ["Goal", "Purpose", "Constraint"].includes(edge.target_type) ? "goal" : "entity",
        dimmed: false,
      });
    }
    for (const edge of focusRelations) {
      add({ id: edge.sourceId, name: edge.sourceName, type: edge.sourceType, kind: "goal", dimmed: false });
      add({ id: edge.targetId, name: edge.targetName, type: edge.targetType, kind: "goal", dimmed: false });
    }

    for (const item of focusProposal?.items || []) {
      if (item.status === "ignored" || item.kind === "gap" || item.kind === "relation") continue;
      add({ id: item.id, name: item.name, type: item.kind, kind: item.kind === "purpose" ? "purpose" : item.kind === "constraint" ? "constraint" : "goal", dimmed: false, status: "proposed" });
    }
    for (const item of focusProposal?.items || []) {
      if (item.status === "ignored" || item.kind !== "relation") continue;
      for (const ref of [item.source, item.target]) {
        if (!ref) continue;
        const candidate = focusProposal?.items.find((entry) => entry.id === ref);
        add({ id: ref, name: candidate?.name || (ref === lensGoalId ? selectedGoal?.name || ref : ref), type: candidate?.kind || "Goal", kind: "goal", dimmed: false, status: candidate ? "proposed" : "confirmed" });
      }
    }

    if (purposeEdges.length === 0 && !linkedIdsForLens) {
      for (const n of brainNodes) {
        add({
          id: n.id,
          name: displayName(n.name, n.id),
          type: n.type,
          kind: "entity",
          dimmed: true,
        });
      }
    }

    let nodes = Array.from(byId.values());
    if (nodes.length > MAX_LENS_NODES) {
      const onEdge = new Set<string>();
      for (const edge of purposeEdges) {
        onEdge.add(edge.source_id);
        onEdge.add(edge.target_id);
      }
      nodes = nodes
        .sort((a, b) => {
          const score = (n: PurposeGraphNode) =>
            (n.kind === "goal" ? 0 : 1) + (onEdge.has(n.id) ? 0 : 2);
          return score(a) - score(b);
        })
        .slice(0, MAX_LENS_NODES);
    }
    return nodes;
  }, [lensGoals, purposeEdges, brainNodes, linkedIdsForLens, focusContext, focusRelations, focusProposal, lensGoalId, selectedGoal]);

  const graphLinks: PurposeGraphLink[] = useMemo(() => {
    const nodeIds = new Set(graphNodes.map((n) => n.id));
    const confirmedEdges = [...purposeEdges, ...focusRelations.map((edge) => ({ source_id: edge.sourceId, target_id: edge.targetId, relationship: edge.relationship }))];
    const confirmed = confirmedEdges
      .filter((edge) => {
        if (!nodeIds.has(edge.source_id) || !nodeIds.has(edge.target_id)) return false;
        if (!linkedIdsForLens) return true;
        return (
          linkedIdsForLens.has(edge.source_id) && linkedIdsForLens.has(edge.target_id)
        );
      })
      .map((edge) => ({
        source: edge.source_id,
        target: edge.target_id,
        relationship: edge.relationship,
        color: relationshipColor(edge.relationship),
        status: "confirmed" as const,
      })).filter((edge, index, all) => all.findIndex((candidate) => candidate.source === edge.source && candidate.target === edge.target && candidate.relationship === edge.relationship) === index);
    const proposed: PurposeGraphLink[] = (focusProposal?.items || [])
      .filter((item) => item.kind === "relation" && item.status !== "ignored" && item.source && item.target && nodeIds.has(item.source) && nodeIds.has(item.target))
      .map((item) => ({ source: item.source!, target: item.target!, relationship: item.relationship || "relation", color: "#a99bf0", status: "proposed" as const }));
    const semantic: PurposeGraphLink[] = [];
    const seen = new Set(confirmed.map((edge) => `${edge.source}|${edge.target}|${edge.relationship}`));
    const pushSemantic = (link: PurposeGraphLink) => {
      const key = `${link.source}|${link.target}|${link.relationship}`;
      if (!nodeIds.has(String(link.source)) || !nodeIds.has(String(link.target)) || seen.has(key)) return;
      seen.add(key);
      semantic.push(link);
    };
    if (lensGoalId) {
      for (const node of focusContext?.purposes || []) {
        pushSemantic({ source: node.id, target: lensGoalId, relationship: "purpose", color: relationshipColor("purpose"), status: "confirmed" });
      }
      for (const node of focusContext?.constraints || []) {
        pushSemantic({ source: node.id, target: lensGoalId, relationship: "constrains", color: relationshipColor("constrains"), status: "confirmed" });
      }
      for (const item of focusProposal?.items || []) {
        if (item.status === "ignored" || item.kind === "gap" || item.kind === "relation") continue;
        const toward = item.kind === "purpose" || item.kind === "constraint";
        pushSemantic({
          source: toward ? item.id : lensGoalId,
          target: toward ? lensGoalId : item.id,
          relationship: item.kind === "purpose" ? "purpose" : item.kind === "constraint" ? "constrains" : "suggests",
          color: "#a99bf0",
          status: "proposed",
        });
      }
    }
    return [...confirmed, ...semantic, ...proposed];
  }, [purposeEdges, focusRelations, graphNodes, linkedIdsForLens, focusProposal, focusContext, lensGoalId]);

  const selectedNode = useMemo(
    () => graphNodes.find((n) => n.id === selectedNodeId) || null,
    [graphNodes, selectedNodeId],
  );

  const detailGoalId = useMemo(() => {
    if (!shouldShowFocusDetail(selectedNodeId) || !lensGoalId) return null;
    if (selectedNodeId === lensGoalId) return lensGoalId;
    if (focusContext?.purposes.some((item) => item.id === selectedNodeId) || focusContext?.constraints.some((item) => item.id === selectedNodeId)) return lensGoalId;
    if (focusProposal?.items.some((item) => item.id === selectedNodeId)) return lensGoalId;
    if (selectedNode?.kind === "entity" || selectedNode?.kind === "other") return lensGoalId;
    return selectedNodeId;
  }, [selectedNodeId, lensGoalId, focusContext, focusProposal, selectedNode]);

  const classicPreset = useMemo(() => {
    const goal = focusContext?.goal || selectedGoal;
    if (!goal || goal.id !== lensGoalId) return null;
    return {
      goal,
      purposes: focusContext?.purposes || [],
      constraints: focusContext?.constraints || [],
      relations: focusRelations,
      proposal: focusProposal,
      children: focusContext?.children || [],
      childTotal: focusContext?.children_total || 0,
    };
  }, [focusContext, selectedGoal, lensGoalId, focusRelations, focusProposal]);

  const edgesForSelected = useMemo(() => {
    if (!selectedNodeId) return [] as GraphAnnotation[];
    return annotations.filter(
      (e) => e.source_id === selectedNodeId || e.target_id === selectedNodeId,
    );
  }, [annotations, selectedNodeId]);

  const yamlGoals = [
    ...(status?.goals ?? []),
    ...(status?.purposes ?? []),
    ...(status?.constraints ?? []),
  ];
  const yamlGoalsTotal =
    (status?.goals_total ?? status?.goals?.length ?? 0) +
    (status?.purposes_total ?? status?.purposes?.length ?? 0) +
    (status?.constraints_total ?? status?.constraints?.length ?? 0);

  async function handleSync() {
    if (!cogniInstance || !datasetId) return;
    setBusy(true);
    try {
      await syncTeleologyGoals(cogniInstance, datasetId);
      await refresh();
      notifications.show({
        title: t(language, "Goals synced", "目标已同步"),
        message: t(language, "Purpose nodes written into this dataset graph.", "目的节点已写入该数据集图谱。"),
        color: "green",
        autoClose: 3500,
      });
    } catch (err) {
      notifications.show({
        title: t(language, "Sync failed", "同步失败"),
        message: err instanceof Error ? err.message : String(err),
        color: "red",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleSyncFromCompanyTree() {
    if (!cogniInstance || !datasetId) return;
    setBusy(true);
    try {
      const result = await syncTeleologyFromCompanyTree(cogniInstance, datasetId);
      await refresh();
      if (result.message && result.tree_goals === 0) {
        notifications.show({
          title: t(language, "No company tree", "没有公司目标树"),
          message: t(
            language,
            result.message,
            "该数据集还没有公司目标树，请先导入/构建目标树。",
          ),
          color: "yellow",
        });
        return;
      }
      notifications.show({
        title: t(language, "Company tree synced", "公司树已同步"),
        message: t(
          language,
          `${result.tree_goals} goals · ${result.advances_created} advances · ${result.serves_created} serves`,
          `${result.tree_goals} 个目标 · ${result.advances_created} 条 advances · ${result.serves_created} 条 serves`,
        ),
        color: "green",
        autoClose: 4500,
      });
    } catch (err) {
      notifications.show({
        title: t(language, "Sync from tree failed", "从目标树同步失败"),
        message: err instanceof Error ? err.message : String(err),
        color: "red",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleAddAnnotation() {
    if (!cogniInstance || !datasetId || !selectedNodeId || !lensGoalId) return;
    if (selectedNode?.kind === "goal") {
      notifications.show({
        title: t(language, "Pick a knowledge node", "请选择知识节点"),
        message: t(language, "Purpose edges go from knowledge → goal.", "目的边应从知识节点指向目标。"),
        color: "yellow",
      });
      return;
    }
    setBusy(true);
    try {
      await createGraphAnnotation(cogniInstance, {
        datasetId,
        sourceId: selectedNodeId,
        targetId: lensGoalId,
        relationship: addRel,
      });
      await refresh();
    } catch (err) {
      notifications.show({
        title: t(language, "Annotate failed", "标注失败"),
        message: err instanceof Error ? err.message : String(err),
        color: "red",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteEdge() {
    const edge = deleteEdge;
    if (!cogniInstance || !datasetId || !edge) return;
    setBusy(true);
    try {
      await deleteGraphAnnotation(cogniInstance, {
        datasetId,
        sourceId: edge.source_id,
        targetId: edge.target_id,
        relationship: edge.relationship,
      });
      setDeleteEdge(null);
      await refresh();
    } catch (err) {
      notifications.show({
        title: t(language, "Remove failed", "移除失败"),
        message: err instanceof Error ? err.message : String(err),
        color: "red",
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleRecall() {
    if (!cogniInstance || !recallQuery.trim() || !lensGoalId) return;
    setBusy(true);
    setRecallResult("");
    try {
      const data = await recallKnowledge(cogniInstance, {
        query: recallQuery.trim(),
        scope: "graph",
        datasetIds: datasetId ? [datasetId] : undefined,
        goalId: lensGoalId,
        goalFilterMode: recallMode,
        searchType: "HYBRID_COMPLETION",
      });
      const items = Array.isArray(data) ? data : [];
      const text = items
        .map((item) => {
          if (typeof item === "string") return item;
          if (item && typeof item === "object") {
            const row = item as Record<string, unknown>;
            const searchResult = row.search_result ?? row.text ?? row.content ?? row;
            return typeof searchResult === "string" ? searchResult : JSON.stringify(searchResult);
          }
          return String(item);
        })
        .join("\n\n---\n\n");
      setRecallResult(text || t(language, "(no results)", "（无结果）"));
    } catch (err) {
      setRecallResult(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSave(input: TeleologyNodeInput) {
    if (!cogniInstance || !editor) return;
    const data =
      editor.mode === "edit" && editor.node
        ? await updateTeleologyNode(cogniInstance, editor.node.id, input)
        : await createTeleologyNode(cogniInstance, input);
    setStatus(data);
    setEditor(null);
    if (datasetId) {
      await syncTeleologyGoals(cogniInstance, datasetId);
      await refresh();
    }
  }

  async function handleDeleteNode() {
    const target = deleteTarget;
    if (!cogniInstance || !target) return;
    setBusy(true);
    try {
      const data = await deleteTeleologyNode(cogniInstance, target.id, target.type as TeleologyNodeType);
      setStatus({
        ...data,
        goals: data.goals ?? [],
        purposes: data.purposes ?? [],
        constraints: data.constraints ?? [],
      });
      setDeleteTarget(null);
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  if (isInitializing || datasetsLoading) {
    return (
      <Shell>
        <TrackPageView page="Teleology" />
        <PageLoading name={t(language, "Teleology", "目的论")} />
      </Shell>
    );
  }

  return (
    <Shell>
      <TrackPageView page="Teleology" />

      {/* Header + purpose lens */}
      <div
        className="onto-top"
        style={{
          padding: "8px 16px 10px",
          flexShrink: 0,
          width: "100%",
          alignItems: "stretch",
          background: "rgba(20, 20, 22, 0.72)",
          borderBottom: "1px solid rgba(255,255,255,0.08)",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        {actionsHost
          ? createPortal(
              <>
                <button
                  type="button"
                  style={btn(true)}
                  disabled={busy || !datasetId}
                  onClick={handleSyncFromCompanyTree}
                  title={t(
                    language,
                    "Read the company tree. This does not generate purpose relations.",
                    "只同步公司树，不会生成目的关系。",
                  )}
                >
                  {t(language, "Sync company tree", "同步公司树")}
                </button>
                <button type="button" style={btn(false)} disabled={busy || !datasetId} onClick={handleSync}>
                  {t(language, "Sync YAML goals", "同步 YAML 目标")}
                </button>
                <button type="button" style={btn(false)} disabled={!datasetId} onClick={() => setCoverageOpen(true)}>
                  {t(language, "Purpose coverage", "目的论覆盖分析")}
                </button>
                <button
                  type="button"
                  style={btn(false)}
                  onClick={() => {
                    setVocabQuery("");
                    setVocabHits([]);
                    setVocabTotal(null);
                    setVocabOpen(true);
                  }}
                >
                  {t(language, "Manage goals", "管理目标")}
                </button>
              </>,
              actionsHost,
            )
          : null}

        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 10,
            alignItems: "center",
          }}
        >
          <label style={{ fontSize: 12, color: "rgba(237,236,234,0.45)", fontWeight: 600 }}>
            {t(language, "Dataset", "数据集")}
          </label>
          <div style={{ position: "relative", minWidth: 160 }}>
            <button
              type="button"
              style={{
                ...selectStyle,
                width: "auto",
                minWidth: 160,
                textAlign: "left",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 8,
              }}
              onClick={() => setDatasetMenuOpen((v) => !v)}
              onBlur={() => window.setTimeout(() => setDatasetMenuOpen(false), 150)}
            >
              <span>{selectedDataset?.name || datasets[0]?.name || t(language, "No datasets", "暂无数据集")}</span>
              <span style={{ opacity: 0.5, fontSize: 10 }}>▾</span>
            </button>
            {datasetMenuOpen ? (
              <div
                style={{
                  position: "absolute",
                  zIndex: 50,
                  top: "100%",
                  left: 0,
                  right: 0,
                  marginTop: 4,
                  maxHeight: 260,
                  overflowY: "auto",
                  background: "#141416",
                  border: "1px solid rgba(255,255,255,0.14)",
                  borderRadius: 8,
                  boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
                }}
              >
                {datasets.length === 0 ? (
                  <div style={{ padding: "8px 12px", color: "rgba(237,236,234,0.45)", fontSize: 13 }}>
                    {t(language, "No datasets", "暂无数据集")}
                  </div>
                ) : (
                  datasets.map((d) => (
                    <button
                      key={d.id}
                      type="button"
                      style={{
                        display: "block",
                        width: "100%",
                        textAlign: "left",
                        padding: "8px 12px",
                        background: d.id === datasetId ? "rgba(188,155,255,0.18)" : "transparent",
                        border: "none",
                        borderTop: "1px solid rgba(255,255,255,0.06)",
                        color: "#EDECEA",
                        cursor: "pointer",
                        fontSize: 13,
                      }}
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => {
                        setSelectedDataset(d);
                        setSelectedNodeId(null);
                        setLensGoalId("");
                        setSelectedGoal(null);
                        setGoalQuery("");
                        setDatasetMenuOpen(false);
                      }}
                    >
                      {d.name}
                    </button>
                  ))
                )}
              </div>
            ) : null}
          </div>

          <span style={{ width: 1, height: 22, background: "rgba(255,255,255,0.1)" }} />

          <span style={{ fontSize: 12, color: "rgba(237,236,234,0.7)" }}>{t(language, "Current purpose", "当前目的")}: {selectedGoal?.name || t(language, "Select from the goal tree", "从左侧目标树选择")}</span>

          <button
            type="button"
            style={btn(true)}
            disabled={!lensGoalId}
            onClick={() => setShowRecall((v) => !v)}
          >
            {t(language, "Recall with this purpose", "用此目的召回")}
          </button>

          <div style={{ display: "flex", gap: 8, marginLeft: "auto", alignItems: "center" }}>
            {(Object.keys(REL_COLOR) as TeleologyRelationship[]).map((rel) => (
              <span key={rel} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "rgba(237,236,234,0.55)" }}>
                <span style={{ width: 10, height: 10, borderRadius: 2, background: REL_COLOR[rel] }} />
                {rel}
              </span>
            ))}
          </div>
        </div>

        {loadError ? (
          <div
            style={{
              padding: "10px 12px",
              borderRadius: 8,
              background: "rgba(248,113,113,0.12)",
              border: "1px solid rgba(248,113,113,0.35)",
              color: "#FECACA",
              fontSize: 13,
            }}
          >
            {t(language, "Graph load failed", "图谱加载失败")}: {loadError}
            {/not found|404/i.test(loadError)
              ? t(
                  language,
                  " — the annotations API returned 404. If /teleology works but /annotations does not, restart the cognee container. If it says dataset not found, pick another dataset.",
                  " — 标注接口返回了 404。若 /teleology 正常而 /annotations 没有，请重启 cognee 容器；若是数据集不存在，请换一个已 cognify 的数据集。",
                )
              : null}
          </div>
        ) : null}

        {showRecall ? (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr auto auto auto",
              gap: 8,
              alignItems: "center",
            }}
          >
            <input
              style={inputStyle}
              value={recallQuery}
              placeholder={t(language, "Ask a question…", "输入问题…")}
              onChange={(e) => setRecallQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleRecall();
              }}
            />
            <select
              style={{ ...selectStyle, width: "auto" }}
              value={recallMode}
              onChange={(e) => setRecallMode(e.target.value as "rerank" | "filter")}
            >
              <option style={optionStyle} value="rerank">rerank</option>
              <option style={optionStyle} value="filter">filter</option>
            </select>
            <button type="button" style={btn(true)} disabled={busy || !recallQuery.trim()} onClick={handleRecall}>
              {t(language, "Recall", "召回")}
            </button>
            <button type="button" style={btn(false)} onClick={() => setShowRecall(false)}>
              {t(language, "Close", "关闭")}
            </button>
            {recallResult ? (
              <pre
                style={{
                  gridColumn: "1 / -1",
                  margin: 0,
                  maxHeight: 160,
                  overflow: "auto",
                  padding: 12,
                  borderRadius: 8,
                  background: "rgba(0,0,0,0.35)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  color: "rgba(237,236,234,0.85)",
                  fontSize: 12,
                  whiteSpace: "pre-wrap",
                }}
              >
                {recallResult}
              </pre>
            ) : null}
          </div>
        ) : null}
      </div>

      {/* Graph + inspector — same shell as the goal hierarchy view */}
      {coverageOpen && cogniInstance && datasetId ? (
        <CoveragePanel instance={cogniInstance} datasetId={datasetId} onClose={() => setCoverageOpen(false)} />
      ) : null}

      <div className="onto-body">
        <SideRail side="left" open={leftOpen} onOpen={() => setLeftOpen(true)} expandLabel={t(language, "Expand goal tree", "展开目标目录")} resizeLabel={t(language, "Resize goal navigation", "调整目标导航宽度")}>
          <GoalNav
            language={language === "zh" ? "zh" : "en"}
            roots={navRoots}
            pages={navPages}
            focusId={lensGoalId || null}
            pathIds={navPath}
            loading={loading}
            statuses={classicNavStatuses}
            emptyLabel={t(language, "No derived goals yet. The company tree stays as data and is not listed as goals.", "还没有派生目标。公司树留在数据层，不会被列成目标。")}
            onPick={(id) => { void pickNavGoal(id); }}
            onExpand={(id, more) => { void expandNav(id, more); }}
            onSearch={searchNav}
            onClose={() => setLeftOpen(false)}
          />
        </SideRail>
        <div className="onto-main" style={{ flex: 1, minWidth: 0, minHeight: 0, position: "relative" }}>
          {graphNodes.length === 0 ? (
            <div className="teleology-canvas-empty">{t(language, "Pick a goal from the tree. Its purpose relations open on the canvas.", "从左侧目标树选择一个目标，目的关系会在画布上展开。")}</div>
          ) : (
            <PurposeLensGraph
              className="teleology-graph-host"
              nodes={graphNodes}
              links={graphLinks}
              selectedNodeId={selectedNodeId}
              onSelectNode={(n) => {
                setSelectedNodeId(n?.id ?? null);
                if (n) setRightOpen(true);
              }}
            />
          )}
        </div>

        <SideRail side="right" open={rightOpen} onOpen={() => setRightOpen(true)} expandLabel={t(language, "Expand details", "展开详情")}>
        <aside className="teleology-classic-inspector">
          <div className="onto-side-head">
            <span>{t(language, "Details", "详情")}</span>
            <button type="button" className="onto-panel-close" onClick={() => setRightOpen(false)} aria-label={t(language, "Collapse details", "收起详情")}>×</button>
          </div>
          <div className="teleology-classic-inspector-body">
          {cogniInstance && detailGoalId ? <GoalFocusDetail
            instance={cogniInstance}
            datasetId={datasetId}
            goalId={detailGoalId}
            preset={detailGoalId === lensGoalId ? classicPreset : null}
            language={language === "zh" ? "zh" : "en"}
            selectedProposalItem={focusProposal?.items.find((item) => item.id === selectedNodeId) || null}
            onSelectProposal={(item) => setSelectedNodeId(item.id)}
            onSelectGoal={(id) => void pickNavGoal(id)}
            onAnalyze={detailGoalId === lensGoalId ? () => { void analyzePurpose(cogniInstance, datasetId, lensGoalId).then((result) => { setFocusProposal(result); setReviewProposal(result); }).catch((cause) => setLoadError(cause instanceof Error ? cause.message : String(cause))); } : undefined}
            onReviewProposal={(next) => setReviewProposal(next)}
          /> : <div style={{ color: "rgba(237,236,234,0.4)", fontSize: 13, lineHeight: 1.5 }}>{t(language, "Click a node to inspect what it is for.", "点击节点，查看它为了什么。")}</div>}
          {!selectedNode ? null : (
            <>
              <div>
                <div style={{ fontSize: 11, color: "rgba(237,236,234,0.45)", fontWeight: 700, letterSpacing: 0.3 }}>
                  {selectedNode.kind === "goal"
                    ? t(language, "PURPOSE", "目的")
                    : t(language, "KNOWLEDGE", "知识")}
                </div>
                <div style={{ fontSize: 16, fontWeight: 700, color: "#EDECEA", marginTop: 4 }}>
                  {selectedNode.name}
                </div>
                <div style={{ fontSize: 12, color: "rgba(237,236,234,0.45)", marginTop: 2 }}>
                  {selectedNode.type}
                </div>
              </div>

              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "rgba(237,236,234,0.55)", marginBottom: 8 }}>
                  {selectedNode.kind === "goal"
                    ? t(language, "What serves it", "谁在服务它")
                    : t(language, "What it is for", "它为了什么")}
                </div>
                {edgesForSelected.length === 0 ? (
                  <div style={{ fontSize: 12, color: "rgba(237,236,234,0.35)" }}>
                    {t(language, "No purpose edges yet.", "还没有目的边。")}
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {edgesForSelected.map((edge) => {
                      const outbound = edge.source_id === selectedNodeId;
                      const other = outbound ? edge.target_name : edge.source_name;
                      return (
                        <div
                          key={`${edge.source_id}:${edge.relationship}:${edge.target_id}`}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 6,
                            padding: "8px 10px",
                            borderRadius: 8,
                            background: "rgba(255,255,255,0.04)",
                            border: "1px solid rgba(255,255,255,0.06)",
                            fontSize: 12,
                            color: "#EDECEA",
                          }}
                        >
                          <span style={{ color: REL_COLOR[edge.relationship] || "#BC9BFF", fontWeight: 700 }}>
                            {outbound ? edge.relationship : `← ${edge.relationship}`}
                          </span>
                          <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
                            {other}
                          </span>
                          <button type="button" style={{ ...btn(false), padding: "4px 8px", fontSize: 11 }} onClick={() => setDeleteEdge(edge)}>
                            ×
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {selectedNode.kind !== "goal" ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "rgba(237,236,234,0.55)" }}>
                    {t(language, "Add purpose edge", "添加目的边")}
                  </div>
                  <div style={{ position: "relative" }}>
                    <input
                      style={inputStyle}
                      value={goalQuery}
                      placeholder={t(language, "Search goal…", "搜索目标…")}
                      onFocus={() => {
                        setGoalMenuOpen(true);
                        if (goalHits.length === 0) {
                          const trimmed = goalQuery.trim();
                          if (trimmed) void searchGoals(trimmed, { mode: "search" });
                          else void searchGoals("", { mode: "browse", parentId: "_roots" });
                        }
                      }}
                      onChange={(e) => {
                        setGoalQuery(e.target.value);
                        setGoalMenuOpen(true);
                      }}
                      onBlur={() => {
                        window.setTimeout(() => setGoalMenuOpen(false), 150);
                      }}
                    />
                    {goalMenuOpen ? (
                      <div
                        style={{
                          position: "absolute",
                          zIndex: 50,
                          top: "100%",
                          left: 0,
                          right: 0,
                          marginTop: 4,
                          maxHeight: 220,
                          overflowY: "auto",
                          background: "#141416",
                          border: "1px solid rgba(255,255,255,0.12)",
                          borderRadius: 8,
                        }}
                      >
                        {goalHits.map((g) => (
                          <button
                            key={g.id}
                            type="button"
                            style={{
                              display: "block",
                              width: "100%",
                              textAlign: "left",
                              padding: "8px 12px",
                              background: "transparent",
                              border: "none",
                              borderTop: "1px solid rgba(255,255,255,0.06)",
                              color: "#EDECEA",
                              cursor: "pointer",
                              fontSize: 13,
                            }}
                            onMouseDown={(e) => e.preventDefault()}
                            onClick={() => pickGoal(g)}
                          >
                            {g.cpd_kind === "goal" ? `CPD · ${g.name}` : g.name}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <select
                    style={selectStyle}
                    value={addRel}
                    onChange={(e) => setAddRel(e.target.value as TeleologyRelationship)}
                  >
                    {(Object.keys(REL_ZH) as TeleologyRelationship[]).map((rel) => (
                      <option style={optionStyle} key={rel} value={rel}>
                        {rel} — {REL_ZH[rel]}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    style={btn(true)}
                    disabled={busy || !lensGoalId}
                    onClick={handleAddAnnotation}
                  >
                    {t(language, "Annotate", "标注")}
                  </button>
                </div>
              ) : null}
            </>
          )}
          </div>
        </aside>
        </SideRail>
      </div>

      {/* Manage goals — searchable / paginated graph goals (not a full YAML dump) */}
      {vocabOpen ? (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.55)",
            zIndex: 40,
            display: "flex",
            justifyContent: "flex-end",
          }}
          onClick={() => setVocabOpen(false)}
        >
          <div
            style={{
              width: 420,
              maxWidth: "100%",
              height: "100%",
              background: "#141416",
              borderLeft: "1px solid rgba(255,255,255,0.08)",
              padding: 20,
              overflow: "auto",
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 700, color: "#EDECEA" }}>
                  {t(language, "Manage goals", "管理目标")}
                </div>
                <div style={{ fontSize: 12, color: "rgba(237,236,234,0.45)", marginTop: 2 }}>
                  {vocabTotal != null
                    ? t(
                        language,
                        `${vocabTotal} in graph — search & load more`,
                        `图谱中共 ${vocabTotal} 个 — 搜索并持续加载`,
                      )
                    : t(language, "Search the graph; nothing is fully loaded.", "在图谱中搜索，不会一次全量加载。")}
                </div>
              </div>
              <button type="button" style={btn(false)} onClick={() => setVocabOpen(false)}>
                {t(language, "Close", "关闭")}
              </button>
            </div>

            <input
              style={inputStyle}
              value={vocabQuery}
              placeholder={t(language, "Search goals…", "搜索目标…")}
              onChange={(e) => setVocabQuery(e.target.value)}
            />

            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                style={btn(true)}
                onClick={() => setEditor({ mode: "create", defaultType: "goal" })}
              >
                {t(language, "New YAML goal", "新建 YAML 目标")}
              </button>
              <button
                type="button"
                style={btn(false)}
                disabled={busy || !cogniInstance}
                onClick={async () => {
                  if (!cogniInstance) return;
                  setBusy(true);
                  try {
                    const data = await loadSampleTeleology(cogniInstance);
                    setStatus(data);
                    if (datasetId) {
                      await syncTeleologyGoals(cogniInstance, datasetId);
                      await refresh();
                    }
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {t(language, "Sample", "示例")}
              </button>
            </div>

            {vocabHits.length === 0 && !vocabLoading ? (
              <div style={{ fontSize: 13, color: "rgba(237,236,234,0.4)" }}>
                {t(language, "No matching goals.", "没有匹配的目标。")}
              </div>
            ) : (
              vocabHits.map((node) => (
                <div
                  key={node.id}
                  style={{
                    display: "flex",
                    gap: 8,
                    padding: 10,
                    borderRadius: 8,
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid rgba(255,255,255,0.06)",
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 650, color: "#EDECEA" }}>
                      {node.cpd_kind === "goal" ? `CPD · ${node.name}` : node.name}
                    </div>
                    <div style={{ fontSize: 11, color: "rgba(237,236,234,0.45)" }}>
                      {node.type}
                      {node.description ? ` · ${node.description.slice(0, 80)}` : ""}
                    </div>
                  </div>
                  <button
                    type="button"
                    style={btn(false)}
                    onClick={() => {
                      pickGoal(node);
                      setVocabOpen(false);
                    }}
                  >
                    {t(language, "Use", "选用")}
                  </button>
                </div>
              ))
            )}

            {vocabLoading ? (
              <div style={{ fontSize: 12, color: "rgba(237,236,234,0.45)" }}>
                {t(language, "Loading…", "加载中…")}
              </div>
            ) : null}

            {vocabHasMore && !vocabLoading ? (
              <button
                type="button"
                style={{ ...btn(false), alignSelf: "stretch" }}
                onClick={() => void loadVocabPage(vocabQuery, vocabHits.length, true)}
              >
                {t(language, "Load more", "加载更多")}
              </button>
            ) : null}

            {yamlGoals.length > 0 ? (
              <>
                <div
                  style={{
                    marginTop: 8,
                    paddingTop: 12,
                    borderTop: "1px solid rgba(255,255,255,0.08)",
                    fontSize: 12,
                    fontWeight: 650,
                    color: "rgba(237,236,234,0.55)",
                  }}
                >
                  {t(
                    language,
                    `YAML vocabulary (${yamlGoals.length}${yamlGoalsTotal > yamlGoals.length ? ` / ${yamlGoalsTotal}` : ""})`,
                    `YAML 词汇表（${yamlGoals.length}${yamlGoalsTotal > yamlGoals.length ? ` / ${yamlGoalsTotal}` : ""}）`,
                  )}
                </div>
                {yamlGoals.map((node) => (
                  <div
                    key={node.id}
                    style={{
                      display: "flex",
                      gap: 8,
                      padding: 10,
                      borderRadius: 8,
                      background: "rgba(255,255,255,0.04)",
                      border: "1px solid rgba(255,255,255,0.06)",
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 650, color: "#EDECEA" }}>{node.name}</div>
                      <div style={{ fontSize: 11, color: "rgba(237,236,234,0.45)" }}>{node.type}</div>
                    </div>
                    <button type="button" style={btn(false)} onClick={() => setEditor({ mode: "edit", node })}>
                      {t(language, "Edit", "编辑")}
                    </button>
                    <button type="button" style={btn(false)} onClick={() => setDeleteTarget(node)}>
                      {t(language, "Delete", "删除")}
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  style={{ ...btn(false), alignSelf: "flex-start" }}
                  onClick={() => setConfirmClear(true)}
                >
                  {t(language, "Clear vocabulary", "清空词汇表")}
                </button>
              </>
            ) : null}
          </div>
        </div>
      ) : null}

      {editor ? (
        <TeleologyNodeModal
          initial={editor.node}
          defaultType={editor.defaultType}
          onClose={() => setEditor(null)}
          onSubmit={handleSave}
        />
      ) : null}

      {reviewProposal && cogniInstance && <PurposeReview instance={cogniInstance} datasetId={datasetId} proposal={reviewProposal} language={language === "zh" ? "zh" : "en"} onClose={() => setReviewProposal(null)} onCommitted={() => { setReviewProposal(null); setFocusProposal(null); setFocusRevision((value) => value + 1); void refresh(); }} />}
      <DeleteConfirmModal
        opened={!!deleteTarget}
        title={t(language, "Delete goal?", "删除目标？")}
        message={deleteTarget ? deleteTarget.name : ""}
        onConfirm={handleDeleteNode}
        onCancel={() => setDeleteTarget(null)}
        busy={busy}
      />
      <DeleteConfirmModal
        opened={!!deleteEdge}
        title={t(language, "Remove annotation?", "移除标注？")}
        message={
          deleteEdge
            ? `${deleteEdge.source_name} —${deleteEdge.relationship}→ ${deleteEdge.target_name}`
            : ""
        }
        onConfirm={handleDeleteEdge}
        onCancel={() => setDeleteEdge(null)}
        busy={busy}
      />
      <DeleteConfirmModal
        opened={confirmClear}
        title={t(language, "Clear vocabulary?", "清空词汇表？")}
        message={t(language, "Deletes the teleology YAML. Graph edges are kept.", "删除目的论 YAML，图谱边仍保留。")}
        onConfirm={async () => {
          if (!cogniInstance) return;
          setBusy(true);
          try {
            const data = await clearTeleology(cogniInstance);
            setStatus({
              ...data,
              goals: data.goals ?? [],
              purposes: data.purposes ?? [],
              constraints: data.constraints ?? [],
            });
            setConfirmClear(false);
          } finally {
            setBusy(false);
          }
        }}
        onCancel={() => setConfirmClear(false)}
        busy={busy}
      />
    </Shell>
  );
}
