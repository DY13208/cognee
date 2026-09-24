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
import NavPanel from "./NavPanel";
import OntologyCanvas from "./OntologyCanvas";
import { classifyKind, displayName } from "./entityMeta";
import { findPath } from "./layoutDag";
import type { EntityKind, OntologyEdge, OntologyEntity, ViewMode } from "./types";
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
}: {
  instance: CogneeInstance;
  datasets: DatasetOpt[];
  selectedDataset: DatasetOpt | null;
  onSelectDataset: (d: DatasetOpt) => void;
  language: "zh" | "en";
  busy: boolean;
  onBusy: (v: boolean) => void;
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

  const [viewMode, setViewMode] = useState<ViewMode>("hierarchy");
  const [hopDepth, setHopDepth] = useState(3);
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

  const [browseHits, setBrowseHits] = useState<{ id: string; name: string; kind: string }[]>([]);
  const [browseLoading, setBrowseLoading] = useState(false);

  const [pathStart, setPathStart] = useState<string | null>(null);
  const [pathEnd, setPathEnd] = useState<string | null>(null);
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
                  relationship:
                    e.label === "has_detail_reference" ? "has_detail_reference" : "has_subgoal",
                  sourceName: displayName(byId.get(e.source)!.name, e.source),
                  targetName: displayName(byId.get(e.target)!.name, e.target),
                  sourceType: "Goal",
                  targetType: "Goal",
                }));
              rootId = tree.rootId;
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
        }

        setEntities(ents);
        setEdges(eds);
        if (rootId) {
          setFocusId(rootId);
          setSelectedId(rootId);
        }
        // Populate browse list with roots / first page of tree
        const childIds = new Set(eds.map((e) => e.targetId));
        const roots = ents.filter((e) => !childIds.has(e.id));
        setBrowseHits(
          (roots.length ? roots : ents).slice(0, 40).map((h) => ({
            id: h.id,
            name: h.name,
            kind: h.kind,
          })),
        );
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
        let eds = edgesFromAnnotations(res.annotations || []);

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
        setBrowseHits(hits.map((h) => ({ id: h.id, name: h.name, kind: h.kind })));
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
    setPathStart(null);
    setPathEnd(null);
    if (datasetId) {
      setBrowseLoading(true);
      void loadConnectedTree().finally(() => setBrowseLoading(false));
    }
  }, [datasetId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!searchOpen) return;
    const h = window.setTimeout(() => void runSearch(searchQ), 220);
    return () => window.clearTimeout(h);
  }, [searchQ, searchOpen, runSearch]);

  const setFocus = useCallback(
    (id: string) => {
      // If the node is already in the loaded CPD tree, just re-center — don't
      // wipe the hierarchy with a 1-hop neighbourhood fetch.
      if (entities.some((e) => e.id === id) && edges.length > 0) {
        setFocusId(id);
        setSelectedId(id);
        return;
      }
      void loadFocus(id, hopDepth);
    },
    [entities, edges, loadFocus, hopDepth],
  );

  const onSelectNode = useCallback(
    (id: string | null) => {
      if (!id) {
        setSelectedId(null);
        return;
      }
      if (viewMode === "path") {
        if (!pathStart) {
          setPathStart(id);
          setSelectedId(id);
          return;
        }
        if (!pathEnd && id !== pathStart) {
          setPathEnd(id);
          setSelectedId(id);
          // ensure both neighbourhoods loaded — use pathStart as focus if needed
          if (focusId !== pathStart) void loadFocus(pathStart, hopDepth);
          return;
        }
        setPathStart(id);
        setPathEnd(null);
        setSelectedId(id);
        return;
      }
      setSelectedId(id);
    },
    [viewMode, pathStart, pathEnd, focusId, hopDepth, loadFocus],
  );

  const visible = useMemo(() => {
    let ents = entities.filter((e) => kindFilter.has(e.kind));
    let eds = edges.filter((e) => !hiddenRels.has(e.relationship));
    eds = eds.filter((e) => {
      const okS = ents.some((x) => x.id === e.sourceId) || e.sourceId === focusId;
      const okT = ents.some((x) => x.id === e.targetId) || e.targetId === focusId;
      return okS && okT;
    });

    if (viewMode === "chain") {
      eds = eds.filter((e) =>
        ["advances", "has_subgoal", "serves"].includes(e.relationship),
      );
    }

    if (viewMode === "path" && pathStart && pathEnd) {
      const path = findPath(eds, pathStart, pathEnd);
      if (path) {
        ents = ents.filter((e) => path.nodeIds.has(e.id));
        eds = eds.filter((e) => path.edgeIds.has(e.id));
      }
    }

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
  }, [entities, edges, kindFilter, hiddenRels, viewMode, pathStart, pathEnd, focusId]);

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
      <header className="onto-top">
        <div className="onto-title-block">
          <div className="onto-title">{t("Teleology", "目的论")}</div>
          <div className="onto-subtitle">
            {t(
              "CPD hierarchy and purpose edges — company tree on open, expand on demand.",
              "打开即加载公司目标树（CPD 层级），再按需展开目的论关系。",
            )}
          </div>
        </div>

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

        <button
          type="button"
          className="onto-btn onto-btn-primary"
          disabled={!focusId}
          onClick={() => focusId && notifications.show({
            title: t("Recall", "召回"),
            message: t("Use Search page with this purpose id in context.", "请在搜索页结合该目的上下文召回。"),
            color: "blue",
          })}
        >
          {t("Recall with this purpose", "用此目的召回")}
        </button>
        <button type="button" className="onto-btn" disabled={busy || !datasetId} onClick={handleSyncTree}>
          {t("From goal tree", "从目标树同步")}
        </button>
        <button type="button" className="onto-btn" disabled={busy || !datasetId} onClick={handleSyncYaml}>
          {t("Sync YAML", "同步 YAML")}
        </button>
      </header>

      <div className="onto-body">
        <NavPanel
          language={language}
          viewMode={viewMode}
          onViewMode={setViewMode}
          hopDepth={hopDepth}
          onHopDepth={setHopDepth}
          relatedOnly={relatedOnly}
          onRelatedOnly={setRelatedOnly}
          hiddenRels={hiddenRels}
          onToggleRel={(rel) => {
            setHiddenRels((prev) => {
              const next = new Set(prev);
              if (next.has(rel)) next.delete(rel);
              else next.add(rel);
              return next;
            });
          }}
          kindFilter={kindFilter}
          onToggleKind={(k) => {
            setKindFilter((prev) => {
              const next = new Set(prev);
              if (next.has(k)) next.delete(k);
              else next.add(k);
              return next;
            });
          }}
          browseHits={browseHits}
          browseLoading={browseLoading || searching}
          onPickBrowse={(id) => setFocus(id)}
          pathStart={pathStart}
          pathEnd={pathEnd}
          onClearPath={() => {
            setPathStart(null);
            setPathEnd(null);
          }}
        />

        <div className="onto-main">
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
            onSelect={onSelectNode}
            onSetFocus={setFocus}
            onExpand={(id) => setFocus(id)}
            onCanvasClick={() => setSelectedId(null)}
            onHover={setHoverId}
            onViewMode={setViewMode}
            onRelatedOnly={setRelatedOnly}
          />
        </div>

        <DetailPanel
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
        />
      </div>
    </div>
  );
}
