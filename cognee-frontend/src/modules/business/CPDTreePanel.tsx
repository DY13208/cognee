"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { CogneeInstance } from "@/modules/instances/types";
import { treeFromCompanyTreeApi, visibleCPDRows, type CompanyTreeApi } from "./cpdTree";
import { useBusinessLanguage } from "./BusinessLanguageContext";

function safeSourceUrl(value: string): string | undefined {
  try {
    const u = new URL(value);
    return u.origin === "https://xx.stillgroup.net:8989" && u.pathname === "/"
      ? u.href
      : undefined;
  } catch {
    return undefined;
  }
}
export default function CPDTreePanel({
  instance,
  datasetId,
  onOpenChange,
}: {
  instance: CogneeInstance;
  datasetId: string;
  onOpenChange?: (open: boolean) => void;
}) {
  const { language } = useBusinessLanguage();
  const t = (zh: string, en: string) => language === "zh" ? zh : en;
  const countLabel = (count: number, zh: string, singular: string, plural: string) =>
    language === "zh" ? `${count} ${zh}` : `${count} ${count === 1 ? singular : plural}`;
  const [open, setOpen] = useState(false),
    [search, setSearch] = useState(""),
    [expanded, setExpanded] = useState<Set<string>>(new Set()),
    [selected, setSelected] = useState<string | null>(null),
    [importing, setImporting] = useState(false),
    [importError, setImportError] = useState("");
  const treeListRef = useRef<HTMLDivElement>(null);
  const query = useQuery({
    queryKey: ["cpd-company-tree", instance.instanceId, datasetId],
    queryFn: async () => {
      const r = await instance.fetch(
        `/v1/datasets/${encodeURIComponent(datasetId)}/company-tree`,
      );
      if (!r.ok) throw new Error(`${t("读取目标树失败", "Failed to load goal tree")} (HTTP ${r.status})`);
      const payload = (await r.json()) as CompanyTreeApi;
      if (payload.missing?.includes("empty") && payload.nodes?.length === 0) return null;
      return treeFromCompanyTreeApi(payload);
    },
    staleTime: 30000,
    retry: false,
    throwOnError: false,
  });
  const tree = query.data;
  const visibleOpen = open && Boolean(tree);
  useEffect(() => {
    onOpenChange?.(visibleOpen);
  }, [visibleOpen, onOpenChange]);
  useEffect(() => {
    if (query.isSuccess && !tree) setOpen(false);
  }, [query.isSuccess, tree]);
  useEffect(() => {
    if (tree) {
      setExpanded(new Set([tree.root.id]));
      setSelected(tree.root.id);
    }
  }, [datasetId, tree?.revision]); // eslint-disable-line react-hooks/exhaustive-deps
  const rows = useMemo(
    () => (tree ? visibleCPDRows(tree, expanded, search) : []),
    [tree, expanded, search],
  );
  const detail = tree?.nodes.find((n) => n.id === selected);
  const primaryGoals = tree?.children.get(tree.root.id)?.filter((n) => n.kind === "goal") || [];
  function selectOutlineGoal(id: string) {
    if (!tree) return;
    setSearch("");
    setSelected(id);
    setExpanded((previous) => new Set([...previous, tree.root.id, id]));
    requestAnimationFrame(() => {
      const row = Array.from(
        treeListRef.current?.querySelectorAll<HTMLElement>("[data-cpd-node-id]") || [],
      ).find((element) => element.dataset.cpdNodeId === id);
      row?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
    });
  }
  async function importLinkedMaps() {
    setImporting(true);
    setImportError("");
    try {
      const response = await instance.fetch(
        `/v1/datasets/${encodeURIComponent(datasetId)}/company-tree/import-links`,
        { method: "POST", timeoutMs: 900000 },
      );
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as {
          detail?: string;
        };
        throw new Error(body.detail || `${t("导入关联脑图失败", "Failed to import linked maps")} (HTTP ${response.status})`);
      }
      await query.refetch();
    } catch (error) {
      setImportError(
        error instanceof Error ? error.message : t("导入关联脑图失败", "Failed to import linked maps"),
      );
    } finally {
      setImporting(false);
    }
  }
  const buttonStyle = {
    padding: "7px 12px",
    border: "1px solid #34445f",
    borderRadius: 8,
    color: "#dce6f7",
    background: "#1a2940",
    cursor: "pointer",
  } as const;
  return (
    <>
      {tree && (
        <div
          role="group"
          aria-label={t("视图切换", "View switch")}
          className="bv-company-view-switch"
        >
          <span className="bv-company-view-label">{t("视图", "View")}</span>
          <div className="bv-company-view-options">
            <button
              type="button"
              aria-pressed={!visibleOpen}
              onClick={() => setOpen(false)}
              className={!visibleOpen ? "bv-company-view-option is-active" : "bv-company-view-option"}
            >
              {t("关系图", "Graph")}
            </button>
            <button
              type="button"
              aria-pressed={visibleOpen}
              onClick={() => setOpen(true)}
              className={visibleOpen ? "bv-company-view-option is-active" : "bv-company-view-option"}
            >
              {t("公司目标树", "Company goal tree")}
            </button>
          </div>
        </div>
      )}
      {query.isError && !tree && (
        <button
          type="button"
          onClick={() => void query.refetch()}
          title={query.error instanceof Error ? query.error.message : t("目标树读取失败", "Failed to load goal tree")}
          className="bv-company-view-retry"
        >
          {t("目标树读取失败，重试", "Goal tree unavailable. Retry")}
        </button>
      )}
      {tree && visibleOpen && (
        <nav aria-label={t("目标目录", "Goal outline")} className="bv-company-outline">
          <div className="bv-company-outline-heading">
            <span>{t("目标目录", "Goal outline")}</span>
            <span>{countLabel(primaryGoals.length, "个分支", "branch", "branches")}</span>
          </div>
          <button
            type="button"
            className={`bv-company-outline-item bv-company-outline-root${selected === tree.root.id ? " is-selected" : ""}`}
            aria-current={selected === tree.root.id ? "true" : undefined}
            onClick={() => selectOutlineGoal(tree.root.id)}
          >
            <span className="bv-company-outline-name">{tree.root.name}</span>
          </button>
          {primaryGoals.map((goal) => {
            const count = tree.children.get(goal.id)?.filter((n) => n.kind === "goal").length || 0;
            return (
              <button
                key={goal.id}
                type="button"
                className={`bv-company-outline-item bv-company-outline-child${selected === goal.id ? " is-selected" : ""}`}
                aria-current={selected === goal.id ? "true" : undefined}
                onClick={() => selectOutlineGoal(goal.id)}
              >
                <span className="bv-company-outline-name">{goal.name}</span>
                <span className="bv-company-outline-count">{count}</span>
              </button>
            );
          })}
        </nav>
      )}
      {tree && (
        <section
          aria-label={t("公司目标树", "Company goal tree")}
          aria-hidden={!visibleOpen}
          className={`bv-company-tree-overlay${visibleOpen ? " is-open" : ""}`}
          onWheel={(e) => e.stopPropagation()}
        >
          <div
            style={{
              flex: 1,
              minHeight: 0,
              margin: "14px 14px 18px 210px",
              background: "#101b2d",
              border: "1px solid #34445f",
              borderRadius: 14,
              display: "flex",
              flexDirection: "column",
              boxShadow: "0 12px 40px #0006",
              overflow: "hidden",
            }}
          >
          <header
            style={{ padding: "18px 22px", borderBottom: "1px solid #2a3652" }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 12,
                alignItems: "center",
              }}
            >
              <div>
                <h2 style={{ fontSize: 20, margin: 0, fontWeight: 650 }}>
                  {t("公司目标树", "Company goal tree")}
                </h2>
                <div style={{ color: "#9eaec6", marginTop: 6 }}>
                  {t("公司模型本图。关联脑图展开后成为下级目标；读不到的链接仍显示未导入。", "Goals from the company model. Linked maps become subgoals when imported; unavailable links remain marked as not imported.")}
                </div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  onClick={() => void importLinkedMaps()}
                  disabled={importing || query.isFetching}
                  style={buttonStyle}
                >
                  {importing ? t("导入中…", "Importing…") : t("导入关联脑图", "Import linked maps")}
                </button>
                <button
                  type="button"
                  onClick={() => query.refetch()}
                  disabled={query.isFetching || importing}
                  style={buttonStyle}
                >
                  {query.isFetching ? t("读取中…", "Loading…") : t("刷新目标树", "Refresh goal tree")}
                </button>
              </div>
            </div>
            {importError && (
              <div role="alert" style={{ marginTop: 12, color: "#ffd39c" }}>
                {importError}
              </div>
            )}
            {tree && (
              <div style={{ marginTop: 12, color: "#62d9dc" }}>
                {t("来源", "Source")} v{tree.revision} · {countLabel(tree.goalCount, "个目标", "goal", "goals")} ·{" "}
                {countLabel(tree.goalEdgeCount, "条目标分解关系", "subgoal link", "subgoal links")} ·{" "}
                {countLabel(tree.referenceCount, "个链接入口", "linked map entry", "linked map entries")} ·{" "}
                {tree.complete ? t("本图层级完整", "Hierarchy complete") : t("本图层级不完整，仍展示已连接目标", "Hierarchy incomplete; showing connected goals")}
              </div>
            )}
          </header>
          {query.isError ? (
            <div role="alert" style={{ padding: 24, color: "#ffd39c" }}>
              {query.error instanceof Error
                ? query.error.message
                : t("目标树读取失败", "Failed to load goal tree")}
              {t("。未将失败或不完整结果解释为空树。", ". Failed or incomplete results are not shown as an empty tree.")}
            </div>
          ) : !tree ? (
            <div role="status" style={{ padding: 24 }}>
              {t("正在读取公司模型层级…", "Loading company model hierarchy…")}
            </div>
          ) : (
            <>
              <div
                style={{
                  display: "flex",
                  gap: 8,
                  padding: "12px 22px",
                  borderBottom: "1px solid #2a3652",
                  flexWrap: "wrap",
                }}
              >
                <input
                  aria-label={t("搜索目标或项目", "Search goals or projects")}
                  placeholder={t("搜索目标或项目，例如 AHC", "Search goals or projects, e.g. AHC")}
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  style={{
                    minWidth: 220,
                    flex: 1,
                    maxWidth: 460,
                    background: "#18263b",
                    border: "1px solid #34445f",
                    borderRadius: 8,
                    padding: "8px 12px",
                    color: "#e9eef6",
                  }}
                />
                <button
                  type="button"
                  onClick={() =>
                    setExpanded(
                      new Set(
                        tree.nodes
                          .filter((n) => tree.children.get(n.id)?.length)
                          .map((n) => n.id),
                      ),
                    )
                  }
                  style={buttonStyle}
                >
                  {t("展开本图全部层级", "Expand all levels")}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setSearch("");
                    setExpanded(new Set([tree.root.id]));
                  }}
                  style={buttonStyle}
                >
                  {t("收起到主线", "Collapse to main branches")}
                </button>
              </div>
              <div
                style={{
                  display: "flex",
                  flex: 1,
                  minHeight: 0,
                  minWidth: 0,
                }}
              >
                <div
                  role="tree"
                  aria-label={t("目标层级", "Goal hierarchy")}
                  ref={treeListRef}
                  style={{
                    flex: "2 1 440px",
                    minHeight: 0,
                    minWidth: 0,
                    overflowY: "auto",
                    overscrollBehavior: "contain",
                    padding: "12px 14px",
                  }}
                >
                  {rows.length === 0 && (
                    <div style={{ padding: 20, color: "#9eaec6" }}>
                      {t("本图中没有匹配项。", "No matching goals in this tree.")}
                    </div>
                  )}
                  {rows.map(({ node, depth }) => {
                    const kids = tree.children.get(node.id) || [],
                      goalKids = kids.filter((n) => n.kind === "goal").length,
                      refKids = kids.length - goalKids;
                    const isExpanded =
                      Boolean(search.trim()) || expanded.has(node.id);
                    return (
                      <div
                        key={node.id}
                        role="treeitem"
                        data-cpd-node-id={node.id}
                        aria-level={depth + 1}
                        aria-expanded={kids.length ? isExpanded : undefined}
                        aria-selected={selected === node.id}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                          minHeight: 43,
                          padding: "5px 10px",
                          paddingLeft: 10 + depth * 23,
                          borderRadius: 8,
                          background:
                            selected === node.id ? "#21344b" : "transparent",
                          borderBottom: "1px solid #ffffff06",
                        }}
                      >
                        {kids.length ? (
                          <button
                            type="button"
                            aria-label={`${isExpanded ? t("收起", "Collapse") : t("展开", "Expand")} ${node.name}`}
                            onClick={() =>
                              setExpanded((prev) => {
                                const n = new Set(prev);
                                if (n.has(node.id)) n.delete(node.id);
                                else n.add(node.id);
                                return n;
                              })
                            }
                            style={{
                              width: 25,
                              flexShrink: 0,
                              color: "#70d9e2",
                              background: "none",
                              border: 0,
                              cursor: "pointer",
                            }}
                          >
                            {isExpanded ? "▾" : "▸"}
                          </button>
                        ) : (
                          <span
                            style={{
                              width: 25,
                              flexShrink: 0,
                              color: "#7e8ca6",
                              textAlign: "center",
                            }}
                          >
                            {node.kind === "map_reference" ? "↗" : "·"}
                          </span>
                        )}
                        <button
                          type="button"
                          onClick={() => setSelected(node.id)}
                          style={{
                            border: 0,
                            background: "none",
                            color: node.kind === "goal" ? "#e9eef6" : "#adbbcf",
                            cursor: "pointer",
                            textAlign: "left",
                            overflowWrap: "anywhere",
                          }}
                        >
                          {node.name}
                        </button>
                        <span
                          style={{
                            marginLeft: "auto",
                            fontSize: 11,
                            color: node.kind === "goal" ? "#6bdedc" : "#d7b777",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {node.kind === "map_reference"
                            ? t("链接 · 未导入", "Link · not imported")
                            : `${goalKids ? countLabel(goalKids, "个子目标", "subgoal", "subgoals") : ""}${goalKids && refKids ? " · " : ""}${refKids ? countLabel(refKids, "个入口", "entry", "entries") : ""}`}
                        </span>
                      </div>
                    );
                  })}
                </div>
                {detail && (
                  <aside
                    aria-label={t("节点来源详情", "Goal source details")}
                    style={{
                      flex: "1 1 250px",
                      maxWidth: 390,
                      minHeight: 0,
                      minWidth: 0,
                      padding: 22,
                      borderLeft: "1px solid #2a3652",
                      overflowY: "auto",
                      overscrollBehavior: "contain",
                      background: "#142034",
                    }}
                  >
                    <div
                      style={{
                        color: "#69d9da",
                        fontSize: 12,
                        marginBottom: 10,
                      }}
                    >
                      {detail.kind === "goal" ? t("C · 目标", "C · Goal") : t("关联脑图入口", "Linked map entry")}
                    </div>
                    <h3
                      style={{
                        fontSize: 18,
                        margin: "0 0 14px",
                        overflowWrap: "anywhere",
                      }}
                    >
                      {detail.name}
                    </h3>
                    {detail.note && (
                      <p style={{ lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
                        {detail.note}
                      </p>
                    )}
                    <p style={{ color: "#b1bfd2", lineHeight: 1.8 }}>
                      {detail.kind === "goal"
                        ? detail.linkedUri
                          ? t("这是从关联脑图展开的目标，下级来自那张图的节点，不代表指标已经计算或目标已经达成。", "This goal expands from a linked map. Its subgoals come from that map; this does not mean the metrics were calculated or the goal was achieved.")
                          : t("这是来源中的目标定义与分解关系，不代表指标已经计算或目标已经达成。", "This shows source goal definitions and their breakdown, not calculated metrics or completed goals.")
                        : t("该节点是公司模型中的引用入口。这次没有读到关联脑图，不能据此断言它没有下级。", "This is a link from the company model. The linked map was unavailable, so its subgoals are unknown.")}
                    </p>
                    <div
                      style={{
                        borderTop: "1px solid #34445f",
                        marginTop: 18,
                        paddingTop: 14,
                        color: "#98abc6",
                        lineHeight: 1.8,
                        overflowWrap: "anywhere",
                      }}
                    >
                      {t("来源版本", "Source version")}: v{detail.revision}
                      <br />
                      {t("来源节点", "Source node")}: {detail.sourceUid}
                    </div>
                    <a
                      href={safeSourceUrl(detail.sourceUri)}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: "block",
                        marginTop: 12,
                        color: "#69d9da",
                      }}
                    >
                      {t("打开公司模型来源 ↗", "Open company model source ↗")}
                    </a>
                    {detail.linkedUri &&
                      safeSourceUrl(detail.linkedUri) && (
                        <a
                          href={safeSourceUrl(detail.linkedUri)}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            display: "block",
                            marginTop: 12,
                            color: "#d7b777",
                          }}
                        >
                          {t("手动打开关联脑图 ↗", "Open linked map ↗")}
                        </a>
                      )}
                  </aside>
                )}
              </div>
            </>
          )}
          </div>
        </section>
      )}
    </>
  );
}
