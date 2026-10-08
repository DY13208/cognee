import type { GoalCandidate, GoalModelView, GraphNodeSummary } from "@/modules/teleology/teleologyApi";
import { buildDerivedGoalTree, isCurrentGoal, type DerivedGoalTree } from "./derivedGoalTree";
import type { OntologyEdge, OntologyEntity } from "./types";

export const BRAND_GROUP_PREFIX = "ui:brands:";
const LABELS: Record<string, string> = { goal: "目标", capability: "能力", driver: "驱动", risk: "风险", constraint: "约束", metric: "指标" };
const RELATIONS = new Set(["advances", "drives", "amplifies", "blocks", "enables", "serves", "constrains", "measures", "sets"]);

export function brandName(name: string): string | null {
  return name.match(/^(?:提升|提高|保障)?\s*(.+?)\s*项目盈利能力$/)?.[1]?.trim() || null;
}

export function hierarchyName(goal: GoalCandidate): string {
  const brand = brandName(goal.name);
  if (brand && !/^(?:各品牌|各|品牌)$/.test(brand)) return brand;
  const names: [RegExp, string][] = [
    [/公司长期.*经营|公司运营/, "公司运营"], [/公司整体经营利润|公司利润/, "公司利润"],
    [/组织能力与人才|公司人事/, "公司人事"], [/经营合规|公司法务/, "公司法务"],
    [/财务健康|公司财务/, "公司财务"], [/AI 与知识|公司AI/, "公司AI"], [/公司行政/, "公司行政"],
  ];
  return names.find(([pattern]) => pattern.test(goal.name))?.[1] || goal.name;
}

/** Virtual grouping changes this read-only projection, never the persisted hierarchy. */
export function buildGoalHierarchyTree(model: GoalModelView, language: "zh" | "en"): DerivedGoalTree {
  const tree = buildDerivedGoalTree(model, language);
  for (const goal of model.candidates) {
    const node = tree.byId.get(goal.id);
    if (node) node.name = hierarchyName(goal);
  }
  for (const [parentId, page] of Object.entries(tree.pages)) {
    page.items = page.items.filter(node => node.type === "Goal" && node.source === "derived_goal");
    const brands = page.items.filter(node => {
      const goal = model.candidates.find(goal => goal.id === node.id);
      const brand = goal && brandName(goal.name);
      return brand && !/^(?:各品牌|各|品牌)$/.test(brand);
    });
    if (brands.length > 1) {
      const id = BRAND_GROUP_PREFIX + parentId;
      const group: GraphNodeSummary = { id, name: `品牌项目（${brands.length}）`, type: "Goal", description: "", source: "derived_goal", parent_id: parentId, child_count: brands.length };
      tree.byId.set(id, group);
      tree.statuses[id] = "UI 分组";
      tree.pages[id] = { items: brands, total: brands.length, nextOffset: brands.length, loaded: true, loading: false };
      page.items = [...page.items.filter(node => !brands.includes(node)), group];
    }
    page.total = page.items.length;
    page.nextOffset = page.items.length;
    const parent = tree.byId.get(parentId);
    if (parent) parent.child_count = page.items.length;
  }
  const originalFocus = tree.focus;
  tree.focus = id => id.startsWith(BRAND_GROUP_PREFIX)
    ? { goal: tree.byId.get(id)!, children: tree.pages[id].items, relations: [], purposes: [], constraints: [] }
    : originalFocus(id);
  return tree;
}

export function projectGoalFocus(model: GoalModelView, tree: DerivedGoalTree, id: string, mode: "hierarchy" | "context") {
  const entities: OntologyEntity[] = [];
  const edges: OntologyEdge[] = [];
  const positions: Record<string, { x: number; y: number }> = {};
  const summary = (node: GraphNodeSummary): OntologyEntity => ({ id: node.id, name: node.name, type: "Goal", kind: "Goal", displayType: node.id.startsWith(BRAND_GROUP_PREFIX) ? "品牌分组" : "目标", childCount: node.child_count, description: brandName(model.candidates.find(goal => goal.id === node.id)?.name || "") ? "项目利润" : undefined });
  const link = (source: GraphNodeSummary, target: GraphNodeSummary) => ({ id: `${source.id}|has_subgoal|${target.id}`, sourceId: source.id, targetId: target.id, sourceName: source.name, targetName: target.name, sourceType: "Goal", targetType: "Goal", relationship: "has_subgoal" });
  const chain = tree.path(id);
  if (mode === "hierarchy" || id.startsWith(BRAND_GROUP_PREFIX)) {
    const children = (tree.pages[id]?.items || []).filter(node => node.type === "Goal");
    entities.push(...[...chain, ...children].map(summary));
    chain.forEach((node, i) => { if (i) edges.push(link(chain[i - 1], node)); });
    if (chain.length) children.forEach(node => edges.push(link(chain[chain.length - 1], node)));
    return { entities, edges, positions: undefined, hasContext: false };
  }
  const current = model.candidates.filter(isCurrentGoal);
  const byId = new Map(current.map(node => [node.id, node]));
  const center = byId.get(id);
  if (!center) return { entities, edges, positions, hasContext: false };
  const relations = model.relations.filter(edge => edge.status !== "rejected" && RELATIONS.has(edge.relationship || "") &&
    ((edge.source_id || edge.source) === id || (edge.target_id || edge.target) === id) &&
    byId.has(edge.source_id || edge.source || "") && byId.has(edge.target_id || edge.target || ""));
  const nodeIds = new Set([id]);
  const upstream = new Set<string>();
  relations.forEach(edge => {
    const source = edge.source_id || edge.source!;
    const target = edge.target_id || edge.target!;
    nodeIds.add(source); nodeIds.add(target);
    if (target === id) upstream.add(source);
    edges.push({ id: edge.id, sourceId: source, targetId: target, sourceName: byId.get(source)!.name, targetName: byId.get(target)!.name, sourceType: byId.get(source)!.node_type || "goal", targetType: byId.get(target)!.node_type || "goal", relationship: edge.relationship! });
  });
  const parent = chain.length > 1 ? chain[chain.length - 2] : null;
  if (parent && byId.has(parent.id)) nodeIds.add(parent.id);
  let left = 0, right = 0, bottom = 0;
  nodeIds.forEach(nodeId => {
    const node = byId.get(nodeId)!;
    const type = node.node_type || "goal";
    const kind = type === "constraint" ? "Constraint" : type === "metric" ? "Metric" : type === "goal" ? "Goal" : "Other";
    entities.push({ id: node.id, name: hierarchyName(node), type, kind, displayType: LABELS[type], description: undefined });
    positions[nodeId] = nodeId === id ? { x: 360, y: 260 } : nodeId === parent?.id ? { x: 360, y: 60 }
      : ["metric", "constraint"].includes(type) ? { x: 80 + bottom++ * 250, y: 530 }
      : ["driver", "capability"].includes(type) || (type === "goal" && upstream.has(nodeId)) ? { x: 60, y: 180 + left++ * 145 }
      : { x: 660, y: 180 + right++ * 145 };
  });
  const bottomY = Math.max(530, 180 + Math.max(left, right) * 145 + 40);
  let bottomIndex = 0;
  entities.filter(node => ["metric", "constraint"].includes(node.type)).forEach(node => {
    positions[node.id] = { x: 60 + (bottomIndex % 3) * 300, y: bottomY + Math.floor(bottomIndex / 3) * 145 };
    bottomIndex += 1;
  });
  return { entities, edges, positions, hasContext: relations.length > 0 };
}
