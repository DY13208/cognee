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
      <span className={`onto-file-icon${hasChildren ? " is-folder" : ""}`} aria-hidden>
        {hasChildren ? <svg width="16" height="14" viewBox="0 0 16 14" fill="currentColor"><path d="M1.5 1C0.671573 1 0 1.67157 0 2.5V11.5C0 12.3284 0.671573 13 1.5 13H14.5C15.3284 13 16 12.3284 16 11.5V4.5C16 3.67157 15.3284 3 14.5 3H8L6.5 1H1.5Z" /></svg> : <svg width="14" height="16" viewBox="0 0 14 16" fill="currentColor" opacity="0.8"><path d="M1.5 0C0.671573 0 0 0.671573 0 1.5V14.5C0 15.3284 0.671573 16 1.5 16H12.5C13.3284 16 14 15.3284 14 14.5V4.5L9.5 0H1.5Z" /><path d="M9 0V4.5H14" fill="currentColor" fillOpacity="0.5" /></svg>}
      </span>
      <button type="button" className={`onto-file-name${hasChildren ? " is-folder" : ""}`} title={node.name} onClick={() => onPick(node.id)}>{node.name}</button>
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
      <div className="onto-file-header"><div className="onto-file-dots"><span /><span /><span /></div><span>explorer</span></div>
      <div className="onto-file-list" role="tree">
        {loading && !tree.length ? <div className="onto-muted">{language === "zh" ? "加载中…" : "Loading…"}</div> : visibleTree.length ? visibleTree.map((node) => <TreeItem key={node.id} node={node} depth={0} selectedId={selectedId} onPick={onPick} language={language} searching={!!query.trim()} />) : <div className="onto-muted">{query ? (language === "zh" ? "没有匹配的目标" : "No matching goals") : (language === "zh" ? "暂无目标，请先同步目标树。" : "No goals yet. Sync the goal tree first.")}</div>}
      </div>
    </div>
  </aside>;
}
