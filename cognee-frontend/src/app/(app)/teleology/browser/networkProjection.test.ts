import { businessNetwork, canvasProjection, clusteredLayout, companyLayout, defaultBusinessGoal, neighborhood } from "./networkProjection";
import { currentNetwork, DEFAULT_TYPES } from "./goalNetwork";
import type { GoalCandidate, GoalModelView, GoalTeleologyItem } from "@/modules/teleology/teleologyApi";
const node = (id: string, node_type = "goal", parent_candidate_id: string | null = null) => ({ id, node_type, parent_candidate_id, name: `${id}项目盈利`, run_id: id === "un" || id === "other" ? "old" : "pilot", status: "confirmed" } as GoalCandidate);
const edge = (source: string, target: string, relationship = "advances", run_id = "pilot") => ({ id: source + target, source, target, relationship, run_id, status: "confirmed" } as GoalTeleologyItem);
const model = { run_id: "pilot", candidates: [node("un"), node("other"), node("sales"), node("procurement"), node("pressure", "driver"), node("risk", "risk"), node("metric", "metric"), node("alone", "goal", "un")], hierarchy: [], relations: [edge("sales", "un"), edge("sales", "procurement"), edge("procurement", "sales"), edge("pressure", "risk", "amplifies"), edge("risk", "un", "blocks"), edge("metric", "un", "measures"), edge("un", "other", "serves", "old")] } as unknown as GoalModelView;
const options = { types: new Set(DEFAULT_TYPES), showSupport: false, expandedGoals: new Set<string>(), focusId: null, hops: 1 as const, loopNodes: new Set<string>(), loopEdges: new Set<string>() };

test("incremental snapshots retain older edges and include explicit business boundary neighbors", () => {
  const fixture: GoalModelView = {
    ...model, submission_mode: "patch", run_id: "latest",
    candidates: [node("aggregate", "goal", "company"), node("brand", "goal", "company"), node("sales", "goal", "brand"), node("unrelated", "goal", "brand"), node("new", "risk")],
    relations: [edge("brand", "aggregate", "advances", "old"), edge("sales", "brand", "advances", "old"), edge("new", "aggregate", "blocks", "latest")],
  };
  expect(currentNetwork(fixture).relations).toHaveLength(3);
  const scoped = businessNetwork(fixture, "aggregate");
  expect(scoped.nodes.map(n => n.id).sort()).toEqual(["aggregate", "brand", "new"]);
  expect(scoped.relations).toHaveLength(2);
  const brand = businessNetwork(fixture, "brand");
  expect(brand.relations.some(r => r.source === "sales" && r.target === "brand")).toBe(true);
});

test("company layout separates projects and preserves ancestry across shared relations", () => {
  const fixture = { ...model, candidates: [node("un"), node("other"), node("child", "goal", "other"), node("driver", "driver"), { ...node("public"), name: "??????" }], relations: [edge("un", "child"), edge("driver", "other")] };
  const before = JSON.stringify(fixture);
  const layout = companyLayout(fixture, fixture.candidates, fixture.relations);
  expect(layout.clusters.map(c => c.rootId)).toEqual(["un", "other", null]);
  const other = layout.clusters.find(c => c.rootId === "other")!;
  for (const id of ["other", "child", "driver"]) {
    const position = layout.positions.find(p => p.node.id === id)!;
    expect(position.x).toBeGreaterThan(other.x);
    expect(position.x).toBeLessThan(other.x + other.width);
    expect(position.y).toBeGreaterThan(other.y);
    expect(position.y).toBeLessThan(other.y + other.height);
  }
  expect(new Set(layout.positions.map(p => p.node.id)).size).toBe(5);
  expect(JSON.stringify(fixture)).toBe(before);
});

test("company project cards form three columns and reserve variable heights", () => {
  const children = Array.from({ length: 9 }, (_, i) => node(`child-${i}`, "goal", "un"));
  const fixture = { ...model, candidates: [node("un"), ...children], relations: [] };
  const layout = companyLayout(fixture, fixture.candidates, [], { "un": 300 });
  expect(layout.clusters).toHaveLength(1);
  expect(new Set(layout.positions.map(p => p.x)).size).toBe(3);
  expect(layout.positions.find(p => p.node.id === "child-2")!.y).toBeGreaterThan(layout.positions[0].y + 300);
});
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
