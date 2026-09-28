"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CogneeInstance } from "@/modules/instances/types";
import {
  getGraphAnnotations,
  syncTeleologyFromCompanyTree,
  syncTeleologyGoals,
  type GraphAnnotation,
  type GraphNodeSummary,
} from "@/modules/teleology/teleologyApi";
import { notifications } from "@mantine/notifications";
import DetailPanel from "./DetailPanel";
import NavPanel, { type GoalTreeNode } from "./NavPanel";
import OntologyCanvas from "./OntologyCanvas";
import { classifyKind, displayName } from "./entityMeta";
import type { EntityKind, OntologyEdge, OntologyEntity } from "./types";
import "./ontology.css";

type DatasetOpt = { id: string; name: string };

function toEntity(g: GraphNodeSummary): OntologyEntity {
  return {
    id: g.id,
    name: displayName(g.name, g.id),
    type: g.type || "Entity",
    kind: classifyKind(g.type || "", g.cpd_kind),
    description: displayName(g.description || ""),
    status: g.status,
    parentName: g.parent_name ? displayName(g.parent_name) : null,
  };
}

function edgesFromAnnotations(anns: GraphAnnotation[]): OntologyEdge[] {
  return anns.map((a, i) => ({
    id: `${a.source_id}|${a.relationship}|${a.target_id}|${i}`,
    sourceId: a.source_id,
    targetId: a.target_id,
    relationship: String(a.relationship),
    sourceName: displayName(a.source_name, a.source_id),
    targetName: displayName(a.target_name, a.target_id),
    sourceType: a.source_type,
    targetType: a.target_type,
  }));
}

function mergeEntitiesFromPayload(
  goals: GraphNodeSummary[],
  nodes: GraphNodeSummary[],
  anns: GraphAnnotation[],
): OntologyEntity[] {
  const map = new Map<string, OntologyEntity>();
  const put = (e: OntologyEntity) => {
    if (!map.has(e.id)) map.set(e.id, e);
  };
  for (const g of goals) put(toEntity(g));
  for (const n of nodes) put(toEntity(n));
  for (const a of anns) {
    put({
      id: a.source_id,
      name: displayName(a.source_name, a.source_id),
      type: a.source_type,
      kind: classifyKind(a.source_type),
    });
    put({
      id: a.target_id,
      name: displayName(a.target_name, a.target_id),
      type: a.target_type,
      kind: classifyKind(a.target_type),
    });
  }
  return [...map.values()];
}

export default function OntologyBrowser({
  instance,
  datasets,
  selectedDataset,
  onSelectDataset,
  language,
  busy,
  onBusy,
  onHeaderCollapsedChange,
}: {
  instance: CogneeInstance;
  datasets: DatasetOpt[];
  selectedDataset: DatasetOpt | null;
  onSelectDataset: (d: DatasetOpt) => void;
  language: "zh" | "en";
  busy: boolean;
  onBusy: (v: boolean) => void;
  onHeaderCollapsedChange?: (collapsed: boolean) => void;
}) {
  const t = (en: string, zh: string) => (language === "zh" ? zh : en);
  const datasetId = selectedDataset?.id || datasets[0]?.id || "";

  const [focusId, setFocusId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [entities, setEntities] = useState<OntologyEntity[]>([]);
  const [edges, setEdges] = useState<OntologyEdge[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadingFocus, setLoadingFocus] = useState(false);

  const viewMode = "hierarchy" as const;
  const hopDepth = 100;
  const [relatedOnly, setRelatedOnly] = useState(false);
  const [hiddenRels, setHiddenRels] = useState<Set<string>>(new Set());
  const [kindFilter, setKindFilter] = useState<Set<EntityKind>>(
    () => new Set(["Goal", "Project", "Metric", "Department", "Person", "Document", "Entity", "Other"]),
  );

  const [searchQ, setSearchQ] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchHits, setSearchHits] = useState<OntologyEntity[]>([]);
  const [searching, setSearching] = useState(false);
  const searchSeq = useRef(0);

  const [goalTree, setGoalTree] = useState<GoalTreeNode[]>([]);
  const [topOpen, setTopOpen] = useState(true);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [zoom, setZoom] = useState(1);
  const mainRef = useRef<HTMLDivElement>(null);
  const [datasetMenu, setDatasetMenu] = useState(false);

  const loadConnectedTree = useCallback(async () => {
      if (!instance || !datasetId) return;
      setLoadingFocus(true);
      setLoadError(null);
      try {
        // Prefer the full company-tree (CPD C→P→D). Fall back to annotations preview.
        let ents: OntologyEntity[] = [];
        let eds: OntologyEdge[] = [];
        let rootId: string | null = null;

        try {
          const treeResp = await instance.fetch(
            `/v1/datasets/${encodeURIComponent(datasetId)}/company-tree`,
          );
          if (treeResp.ok) {
            const tree = (await treeResp.json()) as {
              nodes?: {
                id: string;
                name: string;
                kind?: string;
                note?: string;
              }[];
              edges?: { source: string; target: string; label: string }[];
              rootId?: string | null;
            };
            if (tree.nodes?.length && tree.rootId) {
              const byId = new Map(tree.nodes.map((n) => [n.id, n]));
              ents = tree.nodes.map((n) => ({
                id: n.id,
                name: displayName(n.name, n.id),
                type: "Goal",
                kind: "Goal" as EntityKind,
                description: displayName(n.note || ""),
              }));
              eds = (tree.edges || [])
                .filter((e) => byId.has(e.source) && byId.has(e.target))
                .map((e, i) => ({
                  id: `${e.source}|${e.label}|${e.target}|${i}`,
                  sourceId: e.source,
                  targetId: e.target,
                  relationship: e.label || "has_subgoal",
                  sourceName: displayName(byId.get(e.source)!.name, e.source),
                  targetName: displayName(byId.get(e.target)!.name, e.target),
                  sourceType: "Goal",
                  targetType: "Goal",
                }));
              const childN = new Map<string, number>();
              for (const e of eds) {
                if (e.relationship === "has_subgoal" || e.relationship === "has_detail_reference") {
                  childN.set(e.sourceId, (childN.get(e.sourceId) || 0) + 1);
                }
              }
              ents = ents.map((e) => ({
                ...e,
                childCount: childN.get(e.id) || 0,
              }));
              rootId = tree.rootId;
              const treeNodes = new Map(tree.nodes.map((n) => [n.id, { id: n.id, name: displayName(n.name, n.id), children: [] as GoalTreeNode[] }]));
              const childIds = new Set<string>();
              for (const edge of tree.edges || []) {
                if (edge.label !== "has_subgoal" && edge.label !== "has_detail_reference") continue;
                const parent = treeNodes.get(edge.source);
                const child = treeNodes.get(edge.target);
                if (parent && child && parent !== child) { parent.children.push(child); childIds.add(child.id); }
              }
              setGoalTree([...treeNodes.values()].filter((n) => !childIds.has(n.id)));
              // The company tree only describes hierarchy. Load the focused goal's
              // purpose and knowledge relations from the graph as a separate layer.
              try {
                const related = await getGraphAnnotations(instance, datasetId, { goalId: rootId, limit: 120, goalsLimit: 40 });
                const entityMap = new Map(ents.map((entity) => [entity.id, entity]));
                for (const entity of mergeEntitiesFromPayload(related.goals || [], related.nodes || [], related.annotations || [])) {
                  if (!entityMap.has(entity.id)) entityMap.set(entity.id, entity);
                }
                ents = [...entityMap.values()];
                const seen = new Set(eds.map((edge) => `${edge.sourceId}|${edge.relationship}|${edge.targetId}`));
                for (const edge of edgesFromAnnotations(related.annotations || [])) {
                  const key = `${edge.sourceId}|${edge.relationship}|${edge.targetId}`;
                  if (!seen.has(key)) { eds.push(edge); seen.add(key); }
                }
              } catch { /* keep the company tree when annotations are unavailable */ }
            }
          }
        } catch {
          /* fall through to annotations preview */
        }

        if (!ents.length) {
          const res = await getGraphAnnotations(instance, datasetId, {
            limit: 120,
            goalsLimit: 48,
          });
          ents = mergeEntitiesFromPayload(res.goals || [], res.nodes || [], res.annotations || []);
          eds = edgesFromAnnotations(res.annotations || []);
          rootId = res.goals?.[0]?.id || ents[0]?.id || null;
          setGoalTree((res.goals || []).map((g) => ({ id: g.id, name: displayName(g.name, g.id), children: [] })));
        }

        setEntities(ents);
        setEdges(eds);
        if (rootId) {
          setFocusId(rootId);
          setSelectedId(rootId);
        }
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoadingFocus(false);
      }
    }, [instance, datasetId]);

  const loadFocus = useCallback(
    async (id: string, depth: number) => {
      if (!instance || !datasetId) return;
      // Set focus immediately so the canvas doesn't blank / reflow while fetching.
      setFocusId(id);
      setSelectedId(id);
      setLoadingFocus(true);
      setLoadError(null);
      try {
        const res = await getGraphAnnotations(instance, datasetId, {
          goalId: id,
          limit: 120,
          goalsLimit: 40,
        });
        let ents = mergeEntitiesFromPayload(res.goals || [], res.nodes || [], res.annotations || []);
        const eds = edgesFromAnnotations(res.annotations || []);

        // Approximate hop 2/3 by expanding neighbors once more
        if (depth >= 2) {
          const neighborIds = new Set<string>();
          for (const e of eds) {
            if (e.sourceId === id) neighborIds.add(e.targetId);
            if (e.targetId === id) neighborIds.add(e.sourceId);
          }
          const extras = [...neighborIds].slice(0, depth >= 3 ? 8 : 4);
          for (const nid of extras) {
            try {
              const extra = await getGraphAnnotations(instance, datasetId, {
                goalId: nid,
                limit: 60,
                goalsLimit: 20,
              });
              const moreE = mergeEntitiesFromPayload(
                extra.goals || [],
                extra.nodes || [],
                extra.annotations || [],
              );
              const moreEdges = edgesFromAnnotations(extra.annotations || []);
              const byId = new Map(ents.map((x) => [x.id, x]));
              for (const m of moreE) byId.set(m.id, m);
              ents = [...byId.values()];
              const ek = new Set(eds.map((x) => x.id));
              for (const m of moreEdges) {
                if (!ek.has(m.id)) {
                  eds.push(m);
                  ek.add(m.id);
                }
              }
            } catch {
              /* ignore partial expand failures */
            }
          }
        }

        // hiddenDegree: crude estimate from annotations_total
        const degreeHint = Math.max(
          0,
          (res.annotations_total ?? eds.length) - eds.filter((e) => e.sourceId === id || e.targetId === id).length,
        );
        ents = ents.map((e) =>
          e.id === id ? { ...e, hiddenDegree: degreeHint > 0 ? Math.min(degreeHint, 99) : undefined } : e,
        );

        setEntities(ents);
        setEdges(eds);
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoadingFocus(false);
      }
    },
    [instance, datasetId],
  );

  const runSearch = useCallback(
    async (q: string) => {
      if (!instance || !datasetId) return;
      const seq = ++searchSeq.current;
      setSearching(true);
      try {
        const trimmed = q.trim();
        const res = await getGraphAnnotations(instance, datasetId, {
          q: trimmed || undefined,
          parentId: trimmed ? undefined : "_roots",
          limit: 1,
          goalsLimit: 30,
        });
        if (seq !== searchSeq.current) return;
        const hits = (res.goals || []).map(toEntity);
        setSearchHits(hits);
        // Search hits stay in the dropdown; browse list is the tree walker.
      } catch {
        if (seq !== searchSeq.current) return;
        setSearchHits([]);
      } finally {
        if (seq === searchSeq.current) setSearching(false);
      }
    },
    [instance, datasetId],
  );

  useEffect(() => {
    setFocusId(null);
    setSelectedId(null);
    setEntities([]);
    setEdges([]);
    setGoalTree([]);
    if (datasetId) {
      void loadConnectedTree();
    }
  }, [datasetId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!searchOpen) return;
    const h = window.setTimeout(() => void runSearch(searchQ), 220);
    return () => window.clearTimeout(h);
  }, [searchQ, searchOpen, runSearch]);

  const setFocus = useCallback(
    async (id: string) => {
      setFocusId(id);
      setSelectedId(id);

      // Prefer staying on the loaded company tree — just re-root.
      const children = (() => {
        const map = new Map<string, string[]>();
        for (const e of edges) {
          const rel = e.relationship.toLowerCase();
          if (rel === "has_subgoal" || rel === "has_detail_reference") {
            if (!map.has(e.sourceId)) map.set(e.sourceId, []);
            map.get(e.sourceId)!.push(e.targetId);
          } else if (rel === "advances") {
            if (!map.has(e.targetId)) map.set(e.targetId, []);
            map.get(e.targetId)!.push(e.sourceId);
          }
        }
        return map.get(id) || [];
      })();

      if (entities.some((e) => e.id === id) && (children.length > 0 || edges.length > 0)) {
        // Fetch direct children via parent_id and merge — covers nodes whose
        // CPD subtree wasn't in the initial preview slice.
        if (!instance || !datasetId) return;
        try {
          setLoadingFocus(true);
          const [childrenResult, relationsResult] = await Promise.all([
            getGraphAnnotations(instance, datasetId, { parentId: id, limit: 1, goalsLimit: 60 }),
            getGraphAnnotations(instance, datasetId, { goalId: id, limit: 120, goalsLimit: 40 }),
          ]);
          const kids = (childrenResult.goals || []).map(toEntity);
          const relatedEntities = mergeEntitiesFromPayload(relationsResult.goals || [], relationsResult.nodes || [], relationsResult.annotations || []);
          const relatedEdges = edgesFromAnnotations(relationsResult.annotations || []);
          if (kids.length || relatedEntities.length || relatedEdges.length) {
            setEntities((prev) => {
              const byId = new Map(prev.map((x) => [x.id, x]));
              for (const k of [...kids, ...relatedEntities]) if (!byId.has(k.id)) byId.set(k.id, k);
              return [...byId.values()];
            });
            setEdges((prev) => {
              const ek = new Set(prev.map((x) => `${x.sourceId}|${x.relationship}|${x.targetId}`));
              const next = [...prev];
              for (const k of kids) {
                const key = `${id}|has_subgoal|${k.id}`;
                if (ek.has(key)) continue;
                next.push({
                  id: key,
                  sourceId: id,
                  targetId: k.id,
                  relationship: "has_subgoal",
                  sourceName: entities.find((e) => e.id === id)?.name || id,
                  targetName: k.name,
                  sourceType: "Goal",
                  targetType: "Goal",
                });
                ek.add(key);
              }
              for (const edge of relatedEdges) {
                const key = `${edge.sourceId}|${edge.relationship}|${edge.targetId}`;
                if (!ek.has(key)) { next.push(edge); ek.add(key); }
              }
              return next;
            });
          }
        } catch {
          /* keep current tree */
        } finally {
          setLoadingFocus(false);
        }
        return;
      }
      void loadFocus(id, hopDepth);
    },
    [entities, edges, loadFocus, hopDepth, instance, datasetId],
  );

  const onSelectNode = useCallback(
    (id: string | null) => {
      if (!id) {
        setSelectedId(null);
        return;
      }
      setSelectedId(id);
    },
    [],
  );

  const visible = useMemo(() => {
    let ents = entities.filter((e) => kindFilter.has(e.kind));
    let eds = edges.filter((e) => !hiddenRels.has(e.relationship));
    eds = eds.filter((e) => {
      const okS = ents.some((x) => x.id === e.sourceId) || e.sourceId === focusId;
      const okT = ents.some((x) => x.id === e.targetId) || e.targetId === focusId;
      return okS && okT;
    });

    // Stamp +N for non-focus nodes with unused degree
    const deg = new Map<string, number>();
    for (const e of edges) {
      deg.set(e.sourceId, (deg.get(e.sourceId) || 0) + 1);
      deg.set(e.targetId, (deg.get(e.targetId) || 0) + 1);
    }
    const shown = new Map<string, number>();
    for (const e of eds) {
      shown.set(e.sourceId, (shown.get(e.sourceId) || 0) + 1);
      shown.set(e.targetId, (shown.get(e.targetId) || 0) + 1);
    }
    ents = ents.map((e) => {
      const d = deg.get(e.id) || 0;
      const s = shown.get(e.id) || 0;
      const hidden = Math.max(0, d - s);
      return { ...e, hiddenDegree: hidden > 0 ? hidden : e.hiddenDegree };
    });

    return { entities: ents, edges: eds };
  }, [entities, edges, kindFilter, hiddenRels, focusId]);

  const selectedEntity =
    visible.entities.find((e) => e.id === selectedId) ||
    entities.find((e) => e.id === selectedId) ||
    null;

  async function handleSyncTree() {
    if (!instance || !datasetId) return;
    onBusy(true);
    try {
      const result = await syncTeleologyFromCompanyTree(instance, datasetId);
      notifications.show({
        title: t("Synced", "已同步"),
        message: t(
          `${result.advances_created} advances · ${result.tree_goals} goals`,
          `${result.advances_created} 条 advances · ${result.tree_goals} 个目标`,
        ),
        color: "green",
      });
      if (focusId) void loadFocus(focusId, hopDepth);
      else void loadConnectedTree();
    } catch (err) {
      notifications.show({
        title: t("Sync failed", "同步失败"),
        message: err instanceof Error ? err.message : String(err),
        color: "red",
      });
    } finally {
      onBusy(false);
    }
  }

  async function handleSyncYaml() {
    if (!instance || !datasetId) return;
    onBusy(true);
    try {
      await syncTeleologyGoals(instance, datasetId);
      notifications.show({
        title: t("YAML synced", "YAML 已同步"),
        message: t("Vocabulary written to graph.", "词汇表已写入图谱。"),
        color: "green",
      });
    } catch (err) {
      notifications.show({
        title: t("Sync failed", "同步失败"),
        message: err instanceof Error ? err.message : String(err),
        color: "red",
      });
    } finally {
      onBusy(false);
    }
  }

  return (
    <div className="onto-root">
      <header className={`onto-top${topOpen ? "" : " is-collapsed"}`}>
        {topOpen ? <>
        <div style={{ position: "relative" }}>
          <button
            type="button"
            className="onto-select"
            style={{ minWidth: 140, cursor: "pointer", textAlign: "left" }}
            onClick={() => setDatasetMenu((v) => !v)}
            onBlur={() => window.setTimeout(() => setDatasetMenu(false), 150)}
          >
            {selectedDataset?.name || datasets[0]?.name || t("No dataset", "暂无数据集")} ▾
          </button>
          {datasetMenu ? (
            <div className="onto-search-menu" style={{ minWidth: 160 }}>
              {datasets.map((d) => (
                <button
                  key={d.id}
                  type="button"
                  className="onto-search-item"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => {
                    onSelectDataset(d);
                    setDatasetMenu(false);
                  }}
                >
                  {d.name}
                </button>
              ))}
            </div>
          ) : null}
        </div>

        <div className="onto-search-wrap">
          <input
            className="onto-input"
            style={{ width: "100%", paddingRight: 56 }}
            value={searchQ}
            placeholder={t(
              "Search goals / entities / relationships…",
              "搜索目标 / 实体 / 关系…",
            )}
            onFocus={() => setSearchOpen(true)}
            onChange={(e) => {
              setSearchQ(e.target.value);
              setSearchOpen(true);
            }}
            onBlur={() => window.setTimeout(() => setSearchOpen(false), 180)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
                e.preventDefault();
                (e.target as HTMLInputElement).focus();
              }
            }}
          />
          <span className="onto-kbd">⌘K</span>
          {searchOpen ? (
            <div className="onto-search-menu">
              {searching && searchHits.length === 0 ? (
                <div style={{ padding: 10, fontSize: 12, color: "rgba(232,231,228,0.45)" }}>
                  {t("Searching…", "搜索中…")}
                </div>
              ) : searchHits.length === 0 ? (
                <div style={{ padding: 10, fontSize: 12, color: "rgba(232,231,228,0.45)" }}>
                  {t("No hits", "无结果")}
                </div>
              ) : (
                searchHits.map((h) => (
                  <button
                    key={h.id}
                    type="button"
                    className="onto-search-item"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => {
                      setSearchQ(h.name);
                      setSearchOpen(false);
                      setFocus(h.id);
                    }}
                  >
                    <div style={{ fontSize: 10, color: "rgba(232,231,228,0.4)", fontWeight: 650 }}>
                      {h.kind}
                    </div>
                    {h.name}
                    {h.parentName ? (
                      <div style={{ fontSize: 11, color: "rgba(232,231,228,0.4)" }}>
                        {t("under", "隶属于")} {h.parentName}
                      </div>
                    ) : null}
                  </button>
                ))
              )}
            </div>
          ) : null}
        </div>

        <button type="button" className="onto-btn onto-btn-primary" disabled={!datasetId || loadingFocus} onClick={() => void loadConnectedTree()}>{t("Generate graph", "生成图")}</button>
        <button type="button" className="onto-btn" disabled={busy || !datasetId} onClick={handleSyncTree}>
          {t("Sync goal tree", "同步目标树")}
        </button>
        <button type="button" className="onto-btn" disabled={busy || !datasetId} onClick={handleSyncYaml}>
          {t("Sync YAML", "同步 YAML")}
        </button>
        <div className="onto-more-wrap"><button type="button" className="onto-btn" aria-label={t("More actions", "更多操作")} aria-expanded={moreOpen} onClick={() => setMoreOpen((value) => !value)}>···</button>
          {moreOpen && <div className="onto-more-menu"><button type="button" disabled={!focusId} onClick={() => { setMoreOpen(false); notifications.show({ title: t("Recall", "召回"), message: t("Use Search page with this purpose id in context.", "请在搜索页结合该目的上下文召回。"), color: "blue" }); }}>{t("Recall with this purpose", "用此目的召回")}</button></div>}
        </div>
        </> : <span className="onto-collapsed-title">{t("Teleology ·", "目的论 ·")} {selectedDataset?.name || datasets[0]?.name || t("No dataset", "暂无数据集")}</span>}
        <button type="button" className="onto-btn onto-collapse-btn" onClick={() => { setTopOpen(!topOpen); onHeaderCollapsedChange?.(topOpen); }} aria-expanded={topOpen} aria-label={topOpen ? t("Collapse header", "折叠顶部信息") : t("Expand header", "展开顶部信息")}>
          {topOpen ? t("Collapse header ↑", "收起顶部 ↑") : t("Expand header ↓", "展开顶部 ↓")}
        </button>
      </header>

      <div className="onto-body">
        <div className={`onto-side-container onto-side-left${leftOpen ? "" : " is-collapsed"}`}>
          {leftOpen && <NavPanel language={language} tree={goalTree} selectedId={focusId} loading={loadingFocus} onPick={setFocus} />}
          <button type="button" className="onto-side-handle" onClick={() => setLeftOpen((value) => !value)} aria-label={leftOpen ? t("Collapse goal tree", "收起目标目录") : t("Expand goal tree", "展开目标目录")} aria-expanded={leftOpen}>{leftOpen ? "‹" : "›"}</button>
        </div>

        <div className="onto-main" ref={mainRef}>
          {loadError ? (
            <div style={{ padding: 12, color: "#F87171", fontSize: 12 }}>{loadError}</div>
          ) : null}
          <OntologyCanvas
            focusId={focusId}
            entities={visible.entities}
            edges={visible.edges}
            selectedId={selectedId}
            viewMode={viewMode}
            hopDepth={hopDepth}
            relatedOnly={relatedOnly}
            hiddenRels={hiddenRels}
            hoverId={hoverId}
            language={language}
            loading={loadingFocus}
            zoom={zoom}
            onSelect={onSelectNode}
            onSetFocus={setFocus}
            onExpand={(id) => setFocus(id)}
            onCanvasClick={() => setSelectedId(null)}
            onHover={setHoverId}
          />
          <div className="onto-canvas-toolbar">
            <div className="onto-zoom-group"><button type="button" onClick={() => setZoom((value) => Math.max(0.6, Math.round((value - 0.1) * 10) / 10))} aria-label={t("Zoom out", "缩小")}>−</button><button type="button" onClick={() => setZoom(1)} aria-label={t("Reset zoom", "重置缩放")}>{Math.round(zoom * 100)}%</button><button type="button" onClick={() => setZoom((value) => Math.min(1.6, Math.round((value + 0.1) * 10) / 10))} aria-label={t("Zoom in", "放大")}>＋</button></div>
            <button type="button" className="onto-btn" onClick={() => { if (document.fullscreenElement === mainRef.current) void document.exitFullscreen(); else void mainRef.current?.requestFullscreen(); }} aria-label={t("Toggle fullscreen", "切换全屏")}>⛶</button>
            <div className="onto-toolbar-spacer" />
            <div className="onto-toolbar-filters">
              <button type="button" className="onto-btn" onClick={() => setFiltersOpen((v) => !v)} aria-expanded={filtersOpen}>{t("Display filters", "显示筛选")} ▾</button>
              {filtersOpen && <div className="onto-filter-popover">
                <label className="onto-check"><input type="checkbox" checked={relatedOnly} onChange={(e) => setRelatedOnly(e.target.checked)} />{t("Related nodes only", "仅显示相关节点")}</label>
                <div className="onto-nav-sub">{t("Hide relations", "隐藏关系类型")}</div>
                {["has_subgoal", "has_detail_reference", "serves", "advances", "blocks"].map((rel) => <label key={rel} className="onto-check"><input type="checkbox" checked={hiddenRels.has(rel)} onChange={() => setHiddenRels((prev) => { const next = new Set(prev); if (next.has(rel)) next.delete(rel); else next.add(rel); return next; })} />{rel}</label>)}
                <div className="onto-nav-sub">{t("Entity types", "对象类型")}</div>
                {(["Goal", "Project", "Metric", "Department", "Person", "Document", "Entity", "Other"] as EntityKind[]).map((kind) => <label key={kind} className="onto-check"><input type="checkbox" checked={kindFilter.has(kind)} onChange={() => setKindFilter((prev) => { const next = new Set(prev); if (next.has(kind)) next.delete(kind); else next.add(kind); return next; })} />{kind}</label>)}
              </div>}
            </div>
          </div>
        </div>

        <div className={`onto-side-container onto-side-right${rightOpen ? "" : " is-collapsed"}`}>
        <button type="button" className="onto-side-handle" onClick={() => setRightOpen((value) => !value)} aria-label={rightOpen ? t("Collapse details", "收起目标详情") : t("Expand details", "展开目标详情")} aria-expanded={rightOpen}>{rightOpen ? "›" : "‹"}</button>
        {rightOpen && <DetailPanel
          entity={selectedEntity}
          edges={visible.edges.filter(
            (e) => selectedEntity && (e.sourceId === selectedEntity.id || e.targetId === selectedEntity.id),
          )}
          focusId={focusId}
          language={language}
          onSetFocus={setFocus}
          onSelectNeighbor={(id) => {
            setSelectedId(id);
          }}
        />}
        </div>
      </div>
    </div>
  );
}
