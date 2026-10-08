import type { GoalCandidate, GoalModelView, GoalTeleologyItem } from "@/modules/teleology/teleologyApi";
import { KIND_STRIPE, REL_PILL } from "./entityMeta";

export const NETWORK_TYPES = ["goal", "capability", "risk", "constraint", "metric", "driver"] as const;
export type NetworkType = typeof NETWORK_TYPES[number];
export const NODE_LABELS: Record<NetworkType, string> = {
  goal: "目标", capability: "能力", risk: "风险", constraint: "约束", metric: "指标", driver: "驱动",
};
export const RELATION_LABELS: Record<string, string> = {
  advances: "推进", drives: "驱动", amplifies: "放大", blocks: "阻碍",
  enables: "支撑", serves: "服务于", constrains: "约束", measures: "衡量", sets: "设定",
};
export const CAUSAL_RELATIONS = new Set(["advances", "drives", "amplifies", "blocks"]);
export const DEFAULT_TYPES: NetworkType[] = ["goal", "driver", "risk"];
export const NODE_COLORS: Record<NetworkType, string> = {
  goal: KIND_STRIPE.Goal, capability: KIND_STRIPE.Purpose, risk: REL_PILL.blocks, constraint: KIND_STRIPE.Constraint, metric: KIND_STRIPE.Metric, driver: KIND_STRIPE.Project,
};
export const NODE_ICONS: Record<NetworkType, string> = { goal: "◎", capability: "✦", risk: "⚠", constraint: "⊥", metric: "▦", driver: "↗" };
export function networkType(node: GoalCandidate): NetworkType {
  return NETWORK_TYPES.includes(node.node_type as NetworkType) ? node.node_type as NetworkType : "goal";
}
/** Remove temporary network prefixes only, never company-tree C:person names. */
export function businessName(node: Pick<GoalCandidate, "name" | "description">): string {
  const name = node.name.replace(/^\s*[GPRCMD]\d+\s*(?:[:：.、\-—]\s*|\s+|(?=[\u3400-\u9fff]))/i, "").trim();
  return /^[GPRCMD]\d+$/i.test(name) ? (node.description || "未命名业务节点") : name;
}
export function currentNetwork(model: GoalModelView, currentRunOnly = true) {
  const nodes = [...new Map((model.candidates || []).filter(n => n.status !== "rejected" && n.status !== "legacy_confirmed" && !n.outside_current_snapshot).map(n => [n.id, n])).values()];
  const ids = new Set(nodes.map(n => n.id));
  const relations = (model.relations || []).filter(e => e.status !== "rejected" && e.status !== "legacy_confirmed" && ids.has(sourceOf(e)) && ids.has(targetOf(e)));
  const runRelations = relations.filter(e => e.run_id === model.run_id);
  // A patch is a cumulative snapshot; older unchanged edges remain current.
  if (currentRunOnly && model.submission_mode !== "patch" && model.run_id && runRelations.length) {
    const members = new Set(runRelations.flatMap(e => [sourceOf(e), targetOf(e)]));
    return { nodes: nodes.filter(n => members.has(n.id) || n.run_id === model.run_id), relations: runRelations };
  }
  return { nodes, relations };
}
export const sourceOf = (edge: GoalTeleologyItem) => edge.source_id || edge.source || "";
export const targetOf = (edge: GoalTeleologyItem) => edge.target_id || edge.target || "";
export const edgeKey = (edge: GoalTeleologyItem) => `${sourceOf(edge)}|${edge.relationship}|${targetOf(edge)}`;

export type PositionedNode = { node: GoalCandidate; x: number; y: number };
/** Semantic lanes and a core grid, not a hierarchy or a cycle detector. */
export function layoutNetwork(nodes: GoalCandidate[]): PositionedNode[] {
  const positions: PositionedNode[] = [];
  const count = (type: NetworkType) => nodes.filter(n => networkType(n) === type).length;
  const top = count("constraint") ? 160 + Math.max(0, Math.ceil(count("constraint") / 6) - 1) * 125 : 60;
  const rows = Math.max(count("capability"), count("driver"), Math.ceil(count("goal") / 2), Math.ceil(count("risk") / 2), 1);
  const driverLeft = count("capability") ? 255 : 30;
  const goalLeft = count("driver") ? driverLeft + 225 : count("capability") ? 255 : 30;
  const lanes: Record<NetworkType, [number, number, number]> = {
    capability: [30, top, 1], driver: [driverLeft, top, 1], goal: [goalLeft, top, 2],
    risk: [goalLeft + 510, top, 2], metric: [goalLeft, top + rows * 125 + 30, 3], constraint: [30, 35, 6],
  };
  for (const type of NETWORK_TYPES) {
    const [left, top, columns] = lanes[type];
    nodes.filter(n => networkType(n) === type).forEach((node, index) => {
      positions.push({ node, x: left + (index % columns) * 225, y: top + Math.floor(index / columns) * 125 });
    });
  }
  return positions;
}
