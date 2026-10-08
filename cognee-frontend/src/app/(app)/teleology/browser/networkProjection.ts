import type { GoalCandidate, GoalModelView, GoalTeleologyItem } from "@/modules/teleology/teleologyApi";
import { businessName, CAUSAL_RELATIONS, currentNetwork, networkType, sourceOf, targetOf, type NetworkType, type PositionedNode } from "./goalNetwork";
import { CARD_W } from "./layoutDag";

export type NetworkScope = "global" | "business" | "pilot" | "focus";
export type Network = ReturnType<typeof currentNetwork>;
export const SUPPORT_TYPES: NetworkType[] = ["capability", "metric", "constraint"];
export function businessGoals(model: GoalModelView) {
  const full = currentNetwork(model, false), pilot = currentNetwork(model);
  const members = new Set(pilot.nodes.map(n => n.id));
  const anchors = full.nodes.filter(n => networkType(n) === "goal" && members.has(n.id) && n.run_id !== model.run_id);
  const labelled = full.nodes.filter(n => networkType(n) === "goal" && /项目|品牌/.test(businessName(n)));
  return [...new Map([...anchors, ...labelled].map(n => [n.id, n])).values()];
}
export function defaultBusinessGoal(model: GoalModelView) {
  return businessGoals(model)[0]?.id || currentNetwork(model).nodes.find(n => networkType(n) === "goal")?.id || null;
}
/** Hierarchy is used only as a scope boundary, never as a causal edge. */
export function businessNetwork(model: GoalModelView, rootId: string | null): Network {
  const full = currentNetwork(model, false);
  if (!rootId) return { nodes: [], relations: [] };
  const parent = new Map(full.nodes.map(n => [n.id, n.parent_candidate_id]));
  for (const row of model.hierarchy || []) parent.set(row.id, row.parent_candidate_id);
  const descendants = new Set([rootId]);
  let added = true;
  while (added) {
    added = false;
    for (const n of full.nodes) if (!descendants.has(n.id) && descendants.has(parent.get(n.id) || "")) { descendants.add(n.id); added = true; }
  }
  const pilot = currentNetwork(model);
  const pilotIds = new Set(pilot.nodes.map(n => n.id));
  // A pilot has an explicit submission provenance and existing canonical endpoints.
  // Do not traverse its root's historical edges into company or other projects.
  if (model.submission_mode !== "patch" && model.run_id && pilot.relations.some(e => e.run_id === model.run_id) && pilotIds.has(rootId)) {
    const nodes = full.nodes.filter(n => pilotIds.has(n.id) || descendants.has(n.id));
    const ids = new Set(nodes.map(n => n.id));
    return { nodes, relations: pilot.relations.filter(e => ids.has(sourceOf(e)) && ids.has(targetOf(e))) };
  }
  const boundaries = new Set(businessGoals(model).filter(n => n.id !== rootId).map(n => n.id));
  // Explicit edges at the selected boundary are relevant even when hierarchy differs.
  // Include their endpoints, but do not traverse the rest of another project's subtree.
  const direct = model.submission_mode === "patch" ? neighborhood(new Set([rootId]), full.relations, 1) : new Set<string>();
  const eligible = new Set(full.nodes.filter(n => descendants.has(n.id) || direct.has(n.id) || (!parent.get(n.id) && !boundaries.has(n.id))).map(n => n.id));
  const members = neighborhood(descendants, full.relations.filter(e => eligible.has(sourceOf(e)) && eligible.has(targetOf(e))), "all");
  const nodes = full.nodes.filter(n => members.has(n.id));
  return { nodes, relations: full.relations.filter(e => members.has(sourceOf(e)) && members.has(targetOf(e))) };
}
/** Display neighborhood only; this does not detect loops or derive loop polarity. */
export function neighborhood(seeds: Set<string>, relations: GoalTeleologyItem[], hops: 1 | 2 | "all") {
  const visited = new Set(seeds);
  let frontier = new Set(seeds), depth = 0;
  while (frontier.size && (hops === "all" || depth < hops)) {
    const next = new Set<string>();
    for (const edge of relations) {
      const a = sourceOf(edge), b = targetOf(edge);
      if (frontier.has(a) && !visited.has(b)) next.add(b);
      if (frontier.has(b) && !visited.has(a)) next.add(a);
    }
    for (const id of next) visited.add(id);
    frontier = next; depth++;
  }
  return visited;
}
export function supportingNodes(goalId: string, network: Network, type: NetworkType) {
  const ids = new Set(network.relations.flatMap(e => sourceOf(e) === goalId ? [targetOf(e)] : targetOf(e) === goalId ? [sourceOf(e)] : []));
  return network.nodes.filter(n => networkType(n) === type && ids.has(n.id));
}
/** Explain missing display edges without inventing relations or crossing scopes. */
export function connectionAvailability(network: Network, nodeId: string | null = null) {
  const ids = new Set(network.nodes.map(node => node.id));
  const relations = network.relations.filter(edge => ids.has(sourceOf(edge)) && ids.has(targetOf(edge)) &&
    (!nodeId || sourceOf(edge) === nodeId || targetOf(edge) === nodeId));
  const endpoints = new Set(relations.flatMap(edge => [sourceOf(edge), targetOf(edge)]));
  return {
    total: relations.length,
    causal: relations.filter(edge => CAUSAL_RELATIONS.has(edge.relationship || "")).length,
    supporting: relations.filter(edge => !CAUSAL_RELATIONS.has(edge.relationship || "")).length,
    nodeTypes: new Set(network.nodes.filter(node => endpoints.has(node.id)).map(networkType)),
  };
}
export function canvasProjection(network: Network, options: {
  types: Set<NetworkType>; showSupport: boolean; expandedGoals: Set<string>;
  focusId: string | null; hops: 1 | 2 | "all"; loopNodes: Set<string>; loopEdges: Set<string>;
}) {
  const satellites = new Set<string>();
  const satelliteEdges = new Set<string>();
  for (const key of options.expandedGoals) {
    const [id, selectedType] = key.split("|");
    for (const type of SUPPORT_TYPES.filter(t => !selectedType || t === selectedType)) for (const n of supportingNodes(id, network, type)) {
      satellites.add(n.id);
      satelliteEdges.add(`${id}|${n.id}`); satelliteEdges.add(`${n.id}|${id}`);
    }
  }
  const eligible = network.nodes.filter(n => options.types.has(networkType(n)) || satellites.has(n.id) || options.loopNodes.has(n.id) || n.id === options.focusId);
  const ids = new Set(eligible.map(n => n.id));
  let relations = network.relations.filter(e => ids.has(sourceOf(e)) && ids.has(targetOf(e)) && (
    CAUSAL_RELATIONS.has(e.relationship || "") || options.showSupport ||
    satelliteEdges.has(`${sourceOf(e)}|${targetOf(e)}`) ||
    options.loopEdges.has(`${sourceOf(e)}|${e.relationship}|${targetOf(e)}`)
  ));
  // "All" in Focus means this scope, not the whole company snapshot.
  const focusIds = options.focusId && options.hops !== "all" ? neighborhood(new Set([options.focusId]), relations, options.hops) : ids;
  for (const id of options.loopNodes) focusIds.add(id);
  const considered = eligible.filter(n => focusIds.has(n.id));
  relations = relations.filter(e => focusIds.has(sourceOf(e)) && focusIds.has(targetOf(e)));
  const connected = new Set(relations.flatMap(e => [sourceOf(e), targetOf(e)]));
  return { nodes: considered.filter(n => connected.has(n.id)), isolated: considered.filter(n => !connected.has(n.id)), relations, satellites };
}
export const CLUSTERS = ["销售增长", "渠道经营", "库存采购", "新品", "风险治理"] as const;
export function businessCluster(node: GoalCandidate): string {
  const name = businessName(node);
  if (/新品|上市/.test(name)) return "新品";
  if (/库存|采购|周转|滞销|临期/.test(name)) return "库存采购";
  if (/销售规模|GMV|销售增长|项目盈利/.test(name)) return "销售增长";
  if (/渠道|控价|回款|账期|窜货|破价/.test(name)) return "渠道经营";
  if (/风险|合规|备案|合同|治理/.test(name)) return "风险治理";
  return "销售增长";
}
/** UI-only grouping by business terms; never stored as Goal Model metadata. */
export function companyLayout(model: GoalModelView, nodes: GoalCandidate[], relations: GoalTeleologyItem[], heights: Record<string, number> = {}) {
  const full = currentNetwork(model, false);
  const parents = new Map(full.nodes.map(n => [n.id, n.parent_candidate_id]));
  for (const row of model.hierarchy || []) parents.set(row.id, row.parent_candidate_id);
  const candidates = businessGoals(model).filter(node => /项目盈利|项目利润/.test(businessName(node)) && !/各品牌项目/.test(businessName(node)));
  const anchorIds = new Set(candidates.map(n => n.id));
  const anchors = candidates.filter(node => {
    let cursor = parents.get(node.id);
    const visited = new Set([node.id]);
    while (cursor && !visited.has(cursor)) {
      if (anchorIds.has(cursor)) return false;
      visited.add(cursor); cursor = parents.get(cursor);
    }
    return true;
  });
  const owners = new Map(anchors.map(n => [n.id, n.id]));
  // Prefer explicit ancestry; shared connections never redefine project ownership.
  for (const node of full.nodes) {
    let cursor: string | null | undefined = node.id;
    const visited = new Set<string>();
    while (cursor && !visited.has(cursor)) {
      visited.add(cursor);
      if (owners.has(cursor)) { owners.set(node.id, owners.get(cursor)!); break; }
      cursor = parents.get(cursor);
    }
    if (!owners.has(node.id) && parents.get(node.id)) owners.set(node.id, "company");
  }
  let frontier = [...owners.keys()].filter(id => owners.get(id) !== "company");
  while (frontier.length) {
    const next: string[] = [];
    for (const id of frontier) for (const edge of relations) {
      const other = sourceOf(edge) === id ? targetOf(edge) : targetOf(edge) === id ? sourceOf(edge) : null;
      if (other && !owners.has(other)) { owners.set(other, owners.get(id)!); next.push(other); }
    }
    frontier = next;
  }
  const groups = new Map<string, GoalCandidate[]>();
  for (const node of nodes) {
    const owner = owners.get(node.id) || "company";
    groups.set(owner, [...(groups.get(owner) || []), node]);
  }
  const positions: PositionedNode[] = [];
  const clusters: { name: string; rootId: string | null; x: number; y: number; width: number; height: number }[] = [];
  const columns = Math.max(1, Math.ceil(Math.sqrt(groups.size)));
  const groupWidth = 3 * (CARD_W + 36) + 40;
  let top = 45, index = 0, rowHeight = 0;
  const order = ["driver", "capability", "goal", "risk", "metric", "constraint"];
  for (const [owner, members] of groups) {
    const left = (index % columns) * (groupWidth + 50);
    const sorted = [...members].sort((a, b) => order.indexOf(networkType(a)) - order.indexOf(networkType(b)));
    let y = top + 40;
    for (let start = 0; start < sorted.length; start += 3) {
      const row = sorted.slice(start, start + 3);
      row.forEach((node, column) => positions.push({ node, x: left + 35 + column * (CARD_W + 36), y }));
      y += Math.max(120, ...row.map(n => heights[n.id] || 120)) + 40;
    }
    const height = y - top + 15;
    clusters.push({ name: anchors.find(n => n.id === owner) ? businessName(anchors.find(n => n.id === owner)!) : "公司公共经营", rootId: owner === "company" ? null : owner, x: left + 15, y: top, width: groupWidth, height });
    rowHeight = Math.max(rowHeight, height);
    index++;
    if (index % columns === 0) { top += rowHeight + 50; rowHeight = 0; }
  }
  return { positions, clusters };
}

export function clusteredLayout(nodes: GoalCandidate[], relations: GoalTeleologyItem[], heights: Record<string, number> = {}) {
  const positions: PositionedNode[] = [], clusters: { name: string; x: number; y: number; width: number; height: number }[] = [];
  let top = 45, column = 0, rowHeight = 0, rowLeft = 0;
  const clusterOf = (node: GoalCandidate) => {
    if (SUPPORT_TYPES.includes(networkType(node))) {
      const edge = relations.find(e => (sourceOf(e) === node.id && nodes.some(n => n.id === targetOf(e) && networkType(n) === "goal")) || (targetOf(e) === node.id && nodes.some(n => n.id === sourceOf(e) && networkType(n) === "goal")));
      const goal = edge && nodes.find(n => n.id === (sourceOf(edge) === node.id ? targetOf(edge) : sourceOf(edge)));
      if (goal) return businessCluster(goal);
    }
    return businessCluster(node);
  };
  for (const name of CLUSTERS) {
    const members = nodes.filter(n => clusterOf(n) === name);
    if (!members.length) continue;
    const main = members.filter(n => !SUPPORT_TYPES.includes(networkType(n)));
    const groups = { left: main.filter(n => networkType(n) === "driver"), core: main.filter(n => networkType(n) === "goal"), right: main.filter(n => networkType(n) === "risk") };
    const columnWidth = CARD_W + 36;
    const coreLeft = groups.left.length ? 35 + columnWidth : 35;
    const rightLeft = coreLeft + (groups.core.length > 1 ? columnWidth * 2 : groups.core.length ? columnWidth : 0);
    const local: PositionedNode[] = [];
    for (const [lane, group] of Object.entries(groups)) {
      const columns = lane === "core" ? 2 : 1;
      let rowY = top + 28;
      for (let start = 0; start < group.length; start += columns) {
        const row = group.slice(start, start + columns);
        row.forEach((node, i) => local.push({ node, x: (lane === "left" ? 35 : lane === "core" ? coreLeft : rightLeft) + i * columnWidth, y: rowY }));
        rowY += Math.max(120, ...row.map(n => heights[n.id] || 120)) + 40;
      }
    }
    let supportRow = Math.max(top + 28, ...local.map(p => p.y + (heights[p.node.id] || 120) + 40));
    members.filter(n => SUPPORT_TYPES.includes(networkType(n))).forEach(node => {
      const linked = relations.find(e => sourceOf(e) === node.id || targetOf(e) === node.id);
      const goalId = linked ? sourceOf(linked) === node.id ? targetOf(linked) : sourceOf(linked) : null;
      const goal = local.find(p => p.node.id === goalId && networkType(p.node) === "goal");
      local.push({ node, x: networkType(node) === "metric" ? goal?.x ?? coreLeft : networkType(node) === "capability" ? 35 : rightLeft, y: supportRow });
      supportRow += (heights[node.id] || 120) + 40;
    });
    const height = supportRow - top + 15;
    const clusterWidth = Math.max(CARD_W + 50, ...local.map(p => p.x + CARD_W + 20));
    positions.push(...local.map(p => ({ ...p, x: p.x + rowLeft })));
    clusters.push({ name, x: rowLeft + 15, y: top, width: clusterWidth, height });
    rowHeight = Math.max(rowHeight, height);
    if (column === 1) { top += rowHeight + 35; rowHeight = 0; column = 0; rowLeft = 0; } else { column = 1; rowLeft += clusterWidth + 35; }
  }
  return { positions, clusters };
}
