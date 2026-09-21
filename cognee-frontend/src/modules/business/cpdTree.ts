export interface CPDGraph {
  nodes: Array<{
    id: string;
    type?: string;
    label?: string;
    properties?: Record<string, unknown>;
  }>;
  edges: Array<{ source: string; target: string; label: string }>;
}
export interface CPDNode {
  id: string;
  name: string;
  sourceKey: string;
  sourceUid: string;
  sourceUri: string;
  revision: string;
  kind: "goal" | "map_reference";
  note: string;
  linkedUri: string;
  position: string;
  expectedChildren: number;
  childrenComplete: boolean;
}
export interface CPDTree {
  nodes: CPDNode[];
  root: CPDNode;
  children: Map<string, CPDNode[]>;
  goalCount: number;
  referenceCount: number;
  goalEdgeCount: number;
  revision: string;
  complete: boolean;
}
const ROOM = "room-yk3tz4aj";
const ROOT = "313047eb-0c98-4abb-a1ce-933b1081e234";
export function buildCPDTree(graph: CPDGraph): CPDTree {
  if (!Array.isArray(graph.nodes) || !Array.isArray(graph.edges))
    throw new Error("目标树返回格式不完整");
  const nodes: CPDNode[] = graph.nodes
    .filter(
      (n) =>
        n.properties?.source_room === ROOM &&
        n.properties?.source_scope === "company_model_only",
    )
    .map((n) => {
      const p = n.properties!;
      if (p.cpd_kind !== "goal" && p.cpd_kind !== "map_reference")
        throw new Error("存在未识别的本图节点类型");
      return {
        id: n.id,
        name:
          p.source_text_html === ""
            ? "未命名关联脑图"
            : String(n.label || p.name || ""),
        sourceKey: String(p.source_key || ""),
        sourceUid: String(p.source_uid || ""),
        sourceUri: String(p.source_uri || ""),
        revision: String(p.source_revision || ""),
        kind: p.cpd_kind,
        note: String(p.source_note || ""),
        linkedUri: String(p.linked_map_uri || ""),
        position: String(p.source_position || ""),
        expectedChildren: Number(p.source_child_count),
        childrenComplete: p.source_children_complete === true,
      };
    });
  if (!nodes.length) throw new Error("本图尚未完成导入，请刷新后重试");
  if (
    new Set(nodes.map((n) => n.id)).size !== nodes.length ||
    new Set(nodes.map((n) => n.sourceKey)).size !== nodes.length
  )
    throw new Error("目标树包含重复来源节点");
  const versions = new Set(nodes.map((n) => n.revision));
  if (versions.size !== 1)
    throw new Error("目标树包含多个来源版本，暂不展示完整性结论");
  const roots = nodes.filter((n) => n.sourceUid === ROOT);
  if (roots.length !== 1) throw new Error("公司运营根节点缺失或重复");
  const root = roots[0],
    byId = new Map(nodes.map((n) => [n.id, n])),
    children = new Map(nodes.map((n) => [n.id, [] as CPDNode[]]));
  const parents = new Map<string, string>();
  let goalEdgeCount = 0;
  for (const e of graph.edges) {
    if (e.label !== "has_subgoal" && e.label !== "has_detail_reference")
      continue;
    if (!byId.has(e.source) && !byId.has(e.target)) continue;
    const parent = byId.get(e.source),
      child = byId.get(e.target);
    if (!parent || !child) throw new Error("目标树关系端点不完整");
    if (
      parent.kind !== "goal" ||
      (e.label === "has_subgoal") !== (child.kind === "goal")
    )
      throw new Error("目标与入口关系类型不匹配");
    if (parents.has(e.target)) throw new Error("目标树层级存在重复父关系");
    if (e.target === root.id) throw new Error("根节点存在反向关系或循环");
    parents.set(e.target, e.source);
    children.get(e.source)!.push(child);
    if (e.label === "has_subgoal") goalEdgeCount++;
  }
  for (const n of nodes) {
    const kids = children.get(n.id)!;
    kids.sort((a, b) =>
      a.position < b.position
        ? -1
        : a.position > b.position
          ? 1
          : a.id.localeCompare(b.id),
    );
    if (
      !n.childrenComplete ||
      !Number.isFinite(n.expectedChildren) ||
      kids.length !== n.expectedChildren
    )
      throw new Error("本图下级节点不完整，请等待导入完成后刷新");
  }
  const seen = new Set<string>(),
    visiting = new Set<string>();
  function walk(id: string) {
    if (visiting.has(id)) throw new Error("目标树存在循环");
    visiting.add(id);
    seen.add(id);
    for (const n of children.get(id)!) walk(n.id);
    visiting.delete(id);
  }
  walk(root.id);
  if (seen.size !== nodes.length)
    throw new Error("目标树层级不完整，存在未连接节点");
  return {
    nodes,
    root,
    children,
    goalCount: nodes.filter((n) => n.kind === "goal").length,
    referenceCount: nodes.filter((n) => n.kind === "map_reference").length,
    goalEdgeCount,
    revision: root.revision,
    complete: true,
  };
}
export function visibleCPDRows(
  tree: CPDTree,
  expanded: Set<string>,
  search: string,
): Array<{ node: CPDNode; depth: number }> {
  const query = search.trim().toLocaleLowerCase(),
    included = new Set<string>();
  function mark(n: CPDNode): boolean {
    const descendants = (tree.children.get(n.id) || []).map(mark).some(Boolean);
    const match =
      !query || n.name.toLocaleLowerCase().includes(query) || descendants;
    if (match) included.add(n.id);
    return match;
  }
  mark(tree.root);
  const rows: Array<{ node: CPDNode; depth: number }> = [];
  function walk(n: CPDNode, depth: number) {
    if (!included.has(n.id)) return;
    rows.push({ node: n, depth });
    if (query || expanded.has(n.id))
      for (const c of tree.children.get(n.id) || []) walk(c, depth + 1);
  }
  walk(tree.root, 0);
  return rows;
}
