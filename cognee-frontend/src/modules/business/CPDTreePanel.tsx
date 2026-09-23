"use client";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { CogneeInstance } from "@/modules/instances/types";
import { treeFromCompanyTreeApi, visibleCPDRows, type CompanyTreeApi } from "./cpdTree";

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
  const [open, setOpen] = useState(true),
    [search, setSearch] = useState(""),
    [expanded, setExpanded] = useState<Set<string>>(new Set()),
    [selected, setSelected] = useState<string | null>(null),
    [importing, setImporting] = useState(false),
    [importError, setImportError] = useState("");
  const query = useQuery({
    queryKey: ["cpd-company-tree", instance.instanceId, datasetId],
    queryFn: async () => {
      const r = await instance.fetch(
        `/v1/datasets/${encodeURIComponent(datasetId)}/company-tree`,
      );
      if (!r.ok) throw new Error(`读取目标树失败（HTTP ${r.status}）`);
      return treeFromCompanyTreeApi((await r.json()) as CompanyTreeApi);
    },
    enabled: open,
    staleTime: 30000,
    retry: false,
    throwOnError: false,
  });
  const tree = query.data;
  useEffect(() => {
    onOpenChange?.(open);
  }, [open, onOpenChange]);
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
        throw new Error(
          body.detail || `导入关联脑图失败（HTTP ${response.status}）`,
        );
      }
      await query.refetch();
    } catch (error) {
      setImportError(
        error instanceof Error ? error.message : "导入关联脑图失败",
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
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          ...buttonStyle,
          position: "absolute",
          top: 26,
          left: 180,
          zIndex: 31,
        }}
      >
        {open ? "返回关系图" : "公司目标树"}
      </button>
      {open && (
        <section
          aria-label="公司目标树"
          onWheel={(e) => e.stopPropagation()}
          style={{
            position: "absolute",
            inset: 0,
            zIndex: 30,
            isolation: "isolate",
            pointerEvents: "auto",
            background: "#101b2d",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            overscrollBehavior: "contain",
          }}
        >
          <div
            style={{
              flex: 1,
              minHeight: 0,
              margin: "66px 14px 18px",
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
                  公司目标树
                </h2>
                <div style={{ color: "#9eaec6", marginTop: 6 }}>
                  公司模型本图。关联脑图展开后成为下级目标；读不到的链接仍显示未导入。
                </div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  onClick={() => void importLinkedMaps()}
                  disabled={importing || query.isFetching}
                  style={buttonStyle}
                >
                  {importing ? "导入中…" : "导入关联脑图"}
                </button>
                <button
                  type="button"
                  onClick={() => query.refetch()}
                  disabled={query.isFetching || importing}
                  style={buttonStyle}
                >
                  {query.isFetching ? "读取中…" : "刷新目标树"}
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
                来源 v{tree.revision} · {tree.goalCount} 个目标 ·{" "}
                {tree.goalEdgeCount} 条目标分解关系 · {tree.referenceCount}{" "}
                个链接入口 ·{" "}
                {tree.complete ? "本图层级完整" : "本图层级不完整，仍展示已连接目标"}
              </div>
            )}
          </header>
          {query.isError ? (
            <div role="alert" style={{ padding: 24, color: "#ffd39c" }}>
              {query.error instanceof Error
                ? query.error.message
                : "目标树读取失败"}
              。未将失败或不完整结果解释为空树。
            </div>
          ) : !tree ? (
            <div role="status" style={{ padding: 24 }}>
              正在读取公司模型层级…
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
                  aria-label="搜索目标或项目"
                  placeholder="搜索目标或项目，例如 AHC"
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
                  展开本图全部层级
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setSearch("");
                    setExpanded(new Set([tree.root.id]));
                  }}
                  style={buttonStyle}
                >
                  收起到主线
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
                  aria-label="目标层级"
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
                      本图中没有匹配项。
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
                            aria-label={`${isExpanded ? "收起" : "展开"} ${node.name}`}
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
                            ? "链接 · 未导入"
                            : `${goalKids ? `${goalKids} 个子目标` : ""}${goalKids && refKids ? " · " : ""}${refKids ? `${refKids} 个入口` : ""}`}
                        </span>
                      </div>
                    );
                  })}
                </div>
                {detail && (
                  <aside
                    aria-label="节点来源详情"
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
                      {detail.kind === "goal" ? "C · 目标" : "关联脑图入口"}
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
                          ? "这是从关联脑图展开的目标，下级来自那张图的节点，不代表指标已经计算或目标已经达成。"
                          : "这是来源中的目标定义与分解关系，不代表指标已经计算或目标已经达成。"
                        : "该节点是公司模型中的引用入口。这次没有读到关联脑图，不能据此断言它没有下级。"}
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
                      来源版本：v{detail.revision}
                      <br />
                      来源节点：{detail.sourceUid}
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
                      打开公司模型来源 ↗
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
                          手动打开关联脑图 ↗
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
