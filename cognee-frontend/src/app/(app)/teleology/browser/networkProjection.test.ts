import { businessNetwork, canvasProjection, clusteredLayout, defaultBusinessGoal, neighborhood } from "./networkProjection";
import { currentNetwork, DEFAULT_TYPES } from "./goalNetwork";
import type { GoalCandidate, GoalModelView, GoalTeleologyItem } from "@/modules/teleology/teleologyApi";
const node = (id: string, node_type = "goal", parent_candidate_id: string | null = null) => ({ id, node_type, parent_candidate_id, name: `${id}项目盈利`, run_id: id === "un" || id === "other" ? "old" : "pilot", status: "confirmed" } as GoalCandidate);
const edge = (source: string, target: string, relationship = "advances", run_id = "pilot") => ({ id: source + target, source, target, relationship, run_id, status: "confirmed" } as GoalTeleologyItem);
const model = { run_id: "pilot", candidates: [node("un"), node("other"), node("sales"), node("procurement"), node("pressure", "driver"), node("risk", "risk"), node("metric", "metric"), node("alone", "goal", "un")], hierarchy: [], relations: [edge("sales", "un"), edge("sales", "procurement"), edge("procurement", "sales"), edge("pressure", "risk", "amplifies"), edge("risk", "un", "blocks"), edge("metric", "un", "measures"), edge("un", "other", "serves", "old")] } as unknown as GoalModelView;
const options = { types: new Set(DEFAULT_TYPES), showSupport: false, expandedGoals: new Set<string>(), focusId: null, hops: 1 as const, loopNodes: new Set<string>(), loopEdges: new Set<string>() };
test("business scope excludes other project even across historical relations", () => {
  expect(defaultBusinessGoal(model)).toBe("un");
  expect(businessNetwork(model, "un").nodes.map(n => n.id)).not.toContain("other");
  expect(currentNetwork(model, false).nodes.map(n => n.id)).toContain("other");
});
test("canvas is causal only and removes isolated nodes", () => {
  const result = canvasProjection(businessNetwork(model, "un"), options);
  expect(result.isolated.map(n => n.id)).toContain("alone");
  expect(result.nodes.map(n => n.id)).not.toContain("alone");
  expect(result.nodes.map(n => n.id)).not.toContain("metric");
  expect(result.relations.every(e => e.relationship !== "measures")).toBe(true);
});
test("focus bounds one hop, two hops and all in current scope", () => {
  const network = businessNetwork(model, "un");
  const one = canvasProjection(network, { ...options, focusId: "sales" });
  const two = canvasProjection(network, { ...options, focusId: "sales", hops: 2 });
  expect(one.nodes.map(n => n.id).sort()).toEqual(["procurement", "sales", "un"]);
  expect(two.nodes.map(n => n.id)).toContain("risk");
  expect(two.nodes.map(n => n.id)).not.toContain("pressure");
  expect(canvasProjection(network, { ...options, focusId: "sales", hops: "all" }).nodes.map(n => n.id)).toContain("pressure");
  expect(neighborhood(new Set(["sales"]), network.relations, 1).has("un")).toBe(true);
});
test("metric satellite explicitly expands only its goal relationship", () => {
  const result = canvasProjection(businessNetwork(model, "un"), { ...options, expandedGoals: new Set(["un|metric"]) });
  expect(result.nodes.map(n => n.id)).toContain("metric");
  expect(result.relations.some(e => e.relationship === "measures")).toBe(true);
});
test("support nodes with structural-only edges remain isolated until switch is opened", () => {
  const network = businessNetwork(model, "un"), types = new Set([...DEFAULT_TYPES, "metric" as const]);
  expect(canvasProjection(network, { ...options, types }).isolated.map(n => n.id)).toContain("metric");
  expect(canvasProjection(network, { ...options, types, showSupport: true }).nodes.map(n => n.id)).toContain("metric");
});
test("projection and business clusters never mutate the model", () => {
  const original = JSON.stringify(model);
  const projected = canvasProjection(businessNetwork(model, "un"), options);
  const layout = clusteredLayout(projected.nodes, projected.relations);
  expect(layout.clusters.length).toBeGreaterThan(0);
  expect(new Set(layout.positions.map(n => n.node.id)).size).toBe(projected.nodes.length);
  expect(JSON.stringify(model)).toBe(original);
});
test("layout leaves room below grown cards instead of overlapping the next row", () => {
  const nodes = [node("stock-a"), node("stock-b"), node("stock-c")].map(n => ({ ...n, name: "库存采购目标" }));
  const layout = clusteredLayout(nodes, [], { "stock-a": 320 });
  const first = layout.positions.find(p => p.node.id === "stock-a")!;
  const next = layout.positions.find(p => p.node.id === "stock-c")!;
  expect(next.y).toBeGreaterThan(first.y + 320);
});
