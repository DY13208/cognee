export interface CompanyTreeApiNode {
  id: string;
  name: string;
  kind: "goal" | "map_reference";
  sourceKey?: string;
  sourceUid?: string;
  sourceUri?: string;
  revision?: string;
  note?: string;
  linkedUri?: string;
  position?: string;
  expectedChildren?: number;
  childrenComplete?: boolean;
}
export interface CompanyTreeApiEdge {
  source: string;
  target: string;
  label: string;
}
export interface CompanyTreeApi {
  nodes: CompanyTreeApiNode[];
  edges: CompanyTreeApiEdge[];
  rootId?: string | null;
  revision?: string;
  complete?: boolean;
  missing?: string[];
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

function asNode(n: CompanyTreeApiNode): CPDNode {
  return {
    id: n.id,
    name: n.name,
    sourceKey: n.sourceKey || "",
    sourceUid: n.sourceUid || "",
    sourceUri: n.sourceUri || "",
    revision: n.revision || "",
    kind: n.kind,
    note: n.note || "",
    linkedUri: n.linkedUri || "",
    position: n.position || "",
    expectedChildren: Number(n.expectedChildren),
    childrenComplete: n.childrenComplete === true,
  };
}

export function treeFromCompanyTreeApi(dto: CompanyTreeApi): CPDTree {
  if (!Array.isArray(dto.nodes) || !Array.isArray(dto.edges))
    throw new Error("目标树返回格式不完整");
  if (!dto.nodes.length || !dto.rootId)
    throw new Error("本图尚未完成导入，请刷新后重试");
  const nodes = dto.nodes.map(asNode);
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const root = byId.get(dto.rootId);
  if (!root) throw new Error("公司运营根节点缺失或重复");
  const children = new Map(nodes.map((n) => [n.id, [] as CPDNode[]]));
  let goalEdgeCount = 0;
  for (const e of dto.edges) {
    const parent = byId.get(e.source),
      child = byId.get(e.target);
    if (!parent || !child) continue;
    children.get(e.source)!.push(child);
    if (e.label === "has_subgoal") goalEdgeCount++;
  }
  for (const n of nodes) {
    children.get(n.id)!.sort((a, b) =>
      a.position < b.position
        ? -1
        : a.position > b.position
          ? 1
          : a.id.localeCompare(b.id),
    );
  }
  return {
    nodes,
    root,
    children,
    goalCount: nodes.filter((n) => n.kind === "goal").length,
    referenceCount: nodes.filter((n) => n.kind === "map_reference").length,
    goalEdgeCount,
    revision: dto.revision || root.revision,
    complete: dto.complete === true,
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
