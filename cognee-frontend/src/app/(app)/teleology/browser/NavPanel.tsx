"use client";

import { useEffect, useMemo, useRef, useState } from "react";

export type GoalTreeNode = { id: string; name: string; children: GoalTreeNode[] };

function TreeItem({ node, depth, selectedId, onPick, language, searching }: {
  node: GoalTreeNode;
  depth: number;
  selectedId: string | null;
  onPick: (id: string) => void;
  language: "zh" | "en";
  searching: boolean;
}) {
  const [isOpen, setIsOpen] = useState(true);
  const [isHovered, setIsHovered] = useState(false);
  const hasChildren = node.children.length > 0;
  const expanded = isOpen || searching;

  return <div className="onto-file-item" role="treeitem" aria-expanded={hasChildren ? expanded : undefined} aria-selected={selectedId === node.id}>
    <div className={`onto-file-row${isHovered ? " is-hovered" : ""}${selectedId === node.id ? " is-selected" : ""}`}
      style={{ paddingLeft: depth * 16 + 8 }} onMouseEnter={() => setIsHovered(true)} onMouseLeave={() => setIsHovered(false)}>
      {depth > 0 && <div className="onto-file-guide" style={{ left: (depth - 1) * 16 + 16 }}><div /></div>}
      {hasChildren ? (
        <button type="button" className={`onto-file-chevron${expanded ? " is-open" : ""}`}
          disabled={searching} onClick={() => setIsOpen((value) => !value)}
          aria-label={language === "zh" ? `${expanded ? "收起" : "展开"}${node.name}` : `${expanded ? "Collapse" : "Expand"} ${node.name}`}>
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden><path d="M3.2 1.6L6.8 5L3.2 8.4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
      ) : <span className="onto-file-chevron" aria-hidden />}
      <span className="onto-file-icon" aria-hidden>
        {depth === 0 ? (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z" />
            <path d="M9 13a4.5 4.5 0 0 0 3-4" />
            <path d="M6.003 5.125A3 3 0 0 0 6.401 6.5" />
            <path d="M3.477 10.896a4 4 0 0 1 .585-.396" />
            <path d="M6 18a4 4 0 0 1-1.967-.516" />
            <path d="M12 13h4" />
            <path d="M12 18h6a2 2 0 0 1 2 2v1" />
            <path d="M12 8h8" />
            <path d="M16 8V5a2 2 0 0 1 2-2" />
            <circle cx="16" cy="13" r=".5" />
            <circle cx="18" cy="3" r=".5" />
            <circle cx="20" cy="21" r=".5" />
            <circle cx="20" cy="8" r=".5" />
          </svg>
        ) : (
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <circle cx="12" cy="12" r="6" />
            <circle cx="12" cy="12" r="2" />
          </svg>
        )}
      </span>
      <button type="button" className="onto-file-name" title={node.name} onClick={() => onPick(node.id)}>{node.name}</button>
      <span className="onto-file-hover-dot" aria-hidden />
    </div>
    {hasChildren && <div className={`onto-file-children${expanded ? " is-open" : ""}`} role="group">{expanded && node.children.map((child) => <TreeItem key={child.id} node={child} depth={depth + 1} selectedId={selectedId} onPick={onPick} language={language} searching={searching} />)}</div>}
  </div>;
}

export default function NavPanel({ language, tree, selectedId, loading, onPick }: {
  language: "zh" | "en";
  tree: GoalTreeNode[];
  selectedId: string | null;
  loading: boolean;
  onPick: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const visibleTree = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    if (!term) return tree;
    const filter = (node: GoalTreeNode): GoalTreeNode | null => {
      if (node.name.toLocaleLowerCase().includes(term)) return node;
      const children = node.children.map(filter).filter((child): child is GoalTreeNode => child !== null);
      return children.length ? { ...node, children } : null;
    };
    return tree.map(filter).filter((node): node is GoalTreeNode => node !== null);
  }, [tree, query]);

  useEffect(() => {
    if (!searchOpen) return;
    const timer = window.setTimeout(() => searchInputRef.current?.focus(), 120);
    const onDocClick = (event: MouseEvent) => {
      if (!searchRef.current?.contains(event.target as Node) && query === "") setSearchOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSearchOpen(false);
        setQuery("");
      }
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
    <div className="onto-file-tree">
      <div className="onto-file-header">
        <span>{language === "zh" ? "目标" : "Goals"}</span>
        <div className={`onto-goal-search${searchOpen ? " is-open" : ""}`} ref={searchRef}>
          <button
            type="button"
            className="onto-goal-search-toggle"
            aria-label={searchOpen ? (language === "zh" ? "关闭搜索" : "Close search") : (language === "zh" ? "搜索目标" : "Search goals")}
            aria-expanded={searchOpen}
            onClick={() => {
              setSearchOpen((open) => !open);
              if (searchOpen) setQuery("");
            }}
          >
            {searchOpen ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden><circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" /><path d="M20 20l-3.5-3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
            )}
          </button>
          <form
            className="onto-goal-search-form"
            onSubmit={(event) => {
              event.preventDefault();
              searchInputRef.current?.focus();
            }}
          >
            <input
              ref={searchInputRef}
              className="onto-goal-search-input"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={language === "zh" ? "搜索目标…" : "Search goals…"}
              aria-label={language === "zh" ? "搜索目标" : "Search goals"}
            />
          </form>
        </div>
      </div>
      <div className="onto-file-list" role="tree">
        {loading && !tree.length ? <div className="onto-muted">{language === "zh" ? "加载中…" : "Loading…"}</div> : visibleTree.length ? visibleTree.map((node) => <TreeItem key={node.id} node={node} depth={0} selectedId={selectedId} onPick={onPick} language={language} searching={!!query.trim()} />) : <div className="onto-muted">{query ? (language === "zh" ? "没有匹配的目标" : "No matching goals") : (language === "zh" ? "暂无目标，请先同步目标树。" : "No goals yet. Sync the goal tree first.")}</div>}
      </div>
    </div>
  </aside>;
}
