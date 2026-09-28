"use client";

import { useMemo, useState } from "react";

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
      <button type="button" className={`onto-file-chevron${hasChildren && expanded ? " is-open" : ""}`}
        disabled={!hasChildren || searching} onClick={() => setIsOpen((value) => !value)}
        aria-label={language === "zh" ? `${expanded ? "收起" : "展开"}${node.name}` : `${expanded ? "Collapse" : "Expand"} ${node.name}`}>
        {hasChildren ? <svg width="6" height="8" viewBox="0 0 6 8" fill="none" aria-hidden><path d="M1 1L5 4L1 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg> : <span className="onto-file-leaf-mark">◇</span>}
      </button>
      <span className="onto-file-icon" aria-hidden>
        {hasChildren
          ? <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M6 1.25L10.75 6L6 10.75L1.25 6Z" stroke="currentColor" strokeWidth="1.2" /></svg>
          : <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="2.1" fill="currentColor" /></svg>}
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

  return <aside className="onto-nav">
    <input className="onto-input" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={language === "zh" ? "搜索目标…" : "Search goals…"} aria-label={language === "zh" ? "搜索目标" : "Search goals"} />
    <div className="onto-file-tree">
      <div className="onto-file-header"><span>{language === "zh" ? "目标" : "Goals"}</span></div>
      <div className="onto-file-list" role="tree">
        {loading && !tree.length ? <div className="onto-muted">{language === "zh" ? "加载中…" : "Loading…"}</div> : visibleTree.length ? visibleTree.map((node) => <TreeItem key={node.id} node={node} depth={0} selectedId={selectedId} onPick={onPick} language={language} searching={!!query.trim()} />) : <div className="onto-muted">{query ? (language === "zh" ? "没有匹配的目标" : "No matching goals") : (language === "zh" ? "暂无目标，请先同步目标树。" : "No goals yet. Sync the goal tree first.")}</div>}
      </div>
    </div>
  </aside>;
}
