"use client";

import { useEffect, useRef, useState } from "react";
import type { GraphNodeSummary } from "@/modules/teleology/teleologyApi";

function GoalMark({ depth }: { depth: number }) {
  if (depth === 0) {
    return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z" />
      <path d="M9 13a4.5 4.5 0 0 0 3-4" /><path d="M6.003 5.125A3 3 0 0 0 6.401 6.5" /><path d="M3.477 10.896a4 4 0 0 1 .585-.396" /><path d="M6 18a4 4 0 0 1-1.967-.516" />
      <path d="M12 13h4" /><path d="M12 18h6a2 2 0 0 1 2 2v1" /><path d="M12 8h8" /><path d="M16 8V5a2 2 0 0 1 2-2" />
      <circle cx="16" cy="13" r=".5" /><circle cx="18" cy="3" r=".5" /><circle cx="20" cy="21" r=".5" /><circle cx="20" cy="8" r=".5" />
    </svg>;
  }
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="2" />
  </svg>;
}

export type GoalTreeNode = { id: string; name: string; children: GoalTreeNode[] };
export type GoalPage = { items: GraphNodeSummary[]; total: number; loading: boolean; loaded?: boolean; nextOffset?: number };

export default function NavPanel({ language, roots, pages, focusId, pathIds, loading, onPick, onExpand, onSearch, onClose, hasMoreRoots, onLoadMoreRoots }: {
  language: "zh" | "en";
  roots: GraphNodeSummary[];
  pages: Record<string, GoalPage>;
  focusId: string | null;
  pathIds: string[];
  loading: boolean;
  onPick: (id: string) => void;
  onExpand: (id: string, more?: boolean) => void;
  onSearch: (query: string) => Promise<GraphNodeSummary[]>;
  onClose?: () => void;
  hasMoreRoots?: boolean;
  onLoadMoreRoots?: () => void;
}) {
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [results, setResults] = useState<GraphNodeSummary[]>([]);
  const [searching, setSearching] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { setOpen((old) => new Set([...old, ...pathIds])); }, [pathIds]);
  useEffect(() => {
    if (!query.trim()) return;
    let active = true;
    const timer = window.setTimeout(() => {
      setSearching(true);
      void onSearch(query.trim()).then((found) => { if (active) setResults(found); }).finally(() => { if (active) setSearching(false); });
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [query, onSearch]);
  const t = (en: string, zh: string) => language === "zh" ? zh : en;

  function item(goal: GraphNodeSummary, depth: number, parentId?: string): React.ReactNode {
    const expanded = open.has(goal.id);
    const page = pages[goal.id];
    const count = goal.child_count ?? page?.total ?? 0;
    return <div key={goal.id} role="treeitem" aria-expanded={count ? expanded : undefined} aria-selected={focusId === goal.id}>
      <div className={`onto-file-row${focusId === goal.id ? " is-selected" : ""}`} style={{ paddingLeft: depth * 16 + 8 }}>
        <button type="button" className="onto-file-chevron" aria-label={expanded ? t("Collapse", "收起") : t("Expand", "展开")} onClick={() => {
          const next = new Set(open);
          if (expanded) next.delete(goal.id); else { next.add(goal.id); if (!page?.loaded) onExpand(goal.id); }
          setOpen(next);
        }}>{count ? expanded ? "⌄" : "›" : ""}</button>
        <span className="onto-file-icon" aria-hidden><GoalMark depth={depth} /></span>
        {depth > 0 && <span className="onto-nav-structural">{goal.primary_purpose_id === parentId && goal.primary_purpose_relation ? goal.primary_purpose_relation === "serves" ? t("Serves", "服务于") : t("Advances", "推进") : t("Child", "下级")}</span>}
        <button type="button" className="onto-file-name" title={goal.name} onClick={() => onPick(goal.id)}>{goal.name}</button>
        {count > 0 && <span className="onto-nav-count">{count}</span>}
      </div>
      {expanded && <div role="group" className="onto-nav-branch">
        {page?.loading && <div className="onto-nav-loading">{t("Loading goals…", "加载目标中…")}</div>}
        {page?.items.map((child) => item(child, depth + 1, goal.id))}
        {page?.loaded && (page.nextOffset ?? page.items.length) < page.total && <button type="button" className="onto-nav-more" onClick={() => onExpand(goal.id, true)}>{t("Load 30 more", "再加载 30 个")} · {page.total - (page.nextOffset ?? page.items.length)}</button>}
      </div>}
    </div>;
  }

  useEffect(() => {
    if (!searchOpen) return;
    const timer = window.setTimeout(() => searchInputRef.current?.focus(), 120);
    const onDocClick = (event: MouseEvent) => {
      if (!searchRef.current?.contains(event.target as Node) && query === "") setSearchOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setSearchOpen(false); setQuery(""); setResults([]); }
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [searchOpen, query]);

  return <aside className="onto-nav">
    <div className="onto-file-header">
      <span>{t("Goal navigation", "目标导航")}</span>
      {onClose && <button type="button" className="onto-panel-close" onClick={onClose} aria-label={t("Collapse goal tree", "收起目标目录")}>×</button>}
      <div className={`onto-goal-search${searchOpen ? " is-open" : ""}`} ref={searchRef}>
        <button type="button" className="onto-goal-search-toggle" aria-label={searchOpen ? t("Close search", "关闭搜索") : t("Search goals", "搜索目标")} aria-expanded={searchOpen} onClick={() => { setSearchOpen((value) => !value); if (searchOpen) { setQuery(""); setResults([]); } }}>
          {searchOpen ? <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg> : <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden><circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" /><path d="M20 20l-3.5-3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>}
        </button>
        <form className="onto-goal-search-form" onSubmit={(event) => { event.preventDefault(); searchInputRef.current?.focus(); }}>
          <input ref={searchInputRef} className="onto-goal-search-input" value={query} onChange={(event) => { setQuery(event.target.value); if (!event.target.value) setResults([]); }} placeholder={t("Search goals…", "搜索目标…")} aria-label={t("Search goals", "搜索目标")} />
        </form>
      </div>
    </div>
    <div className="onto-file-list" role="tree">
      {query.trim() ? searching ? <div className="onto-nav-loading">{t("Searching…", "搜索中…")}</div> : results.length ? results.map((goal) => <button type="button" className="onto-nav-result" key={goal.id} onClick={() => { onPick(goal.id); setQuery(""); setResults([]); setSearchOpen(false); }}><span className="onto-file-icon" aria-hidden><GoalMark depth={0} /></span><span>{goal.name}</span><small>{goal.parent_name || t("Root goal", "根目标")}</small></button>) : <div className="onto-nav-loading">{t("No matching goals", "没有匹配的目标")}</div> : loading && !roots.length ? <div className="onto-nav-loading">{t("Loading roots…", "加载根目标中…")}</div> : roots.length ? <>{roots.map((goal) => item(goal, 0))}{hasMoreRoots && <button type="button" className="onto-nav-more" onClick={onLoadMoreRoots}>{t("Load more roots", "加载更多根目标")}</button>}</> : <div className="onto-nav-loading">{t("No goals. Sync the goal tree first.", "暂无目标，请先同步目标树。")}</div>}
    </div>
  </aside>;
}
