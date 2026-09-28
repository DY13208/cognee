import type { GoalTreeNode } from "./NavPanel";

export type CompanyTreePayload = {
  nodes?: { id: string; name: string; kind?: string; note?: string }[];
  edges?: { source: string; target: string; label: string }[];
  rootId?: string | null;
};

export function buildGoalTree(payload: CompanyTreePayload, cleanName: (name: string, id: string) => string): GoalTreeNode[] {
  const nodes = new Map((payload.nodes || []).map((node) => [node.id, { id: node.id, name: cleanName(node.name, node.id), children: [] as GoalTreeNode[] }]));
  const childIds = new Set<string>();
  for (const edge of payload.edges || []) {
    if (edge.label !== "has_subgoal" && edge.label !== "has_detail_reference") continue;
    const parent = nodes.get(edge.source);
    const child = nodes.get(edge.target);
    if (parent && child && parent !== child && !childIds.has(child.id)) {
      parent.children.push(child);
      childIds.add(child.id);
    }
  }
  return [...nodes.values()].filter((node) => !childIds.has(node.id));
}
