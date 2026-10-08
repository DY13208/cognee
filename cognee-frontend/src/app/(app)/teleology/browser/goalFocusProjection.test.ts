import type { GoalCandidate, GoalModelView } from "@/modules/teleology/teleologyApi";
import { buildGoalHierarchyTree, projectGoalFocus } from "./goalFocusProjection";

const node = (id: string, name: string, parent: string | null, type: GoalCandidate["node_type"] = "goal") => ({ id, name, parent_candidate_id: parent, node_type: type, status: "confirmed", source_node_ids: ["C-source"], evidence: [{ node_id: "C-source", name: "林艺鹏 C:品牌项目利润分" }], confidence: .8 } as GoalCandidate);
const model = { candidates: [node("company", "公司运营", null), node("profit", "公司利润", "company"), node("brand", "提升 DR.BANGGIWON 项目盈利能力", "profit"), node("un", "提升 UN 项目盈利能力", "profit"), ...["capability", "driver", "risk", "metric", "constraint"].map(type => node(type, type, null, type as GoalCandidate["node_type"]))], hierarchy: [], relations: [], purposes: [], constraints: [] } as unknown as GoalModelView;

it("hierarchy contains ancestors, focus and direct children only, never evidence", () => {
  const tree = buildGoalHierarchyTree(model, "zh");
  const result = projectGoalFocus(model, tree, "brand", "hierarchy");
  expect(result.entities.map(node => node.id)).toEqual(["company", "profit", "brand"]);
  expect(result.entities.every(node => node.kind === "Goal")).toBe(true);
  expect(result.edges.map(edge => edge.relationship)).toEqual(["has_subgoal", "has_subgoal"]);
  expect(result.entities.find(node => node.id === "brand")?.name).toBe("DR.BANGGIWON");
});

it("groups brands in a virtual page without altering canonical data", () => {
  const before = JSON.stringify(model);
  const tree = buildGoalHierarchyTree(model, "zh");
  expect(tree.pages.profit.items.map(node => node.name)).toEqual(["品牌项目（2）"]);
  const group = tree.pages.profit.items[0];
  expect(tree.pages[group.id].items.map(node => node.id)).toEqual(["brand", "un"]);
  expect(projectGoalFocus(model, tree, "profit", "hierarchy").entities.map(node => node.id)).not.toContain("brand");
  expect(projectGoalFocus(model, tree, group.id, "hierarchy").entities.map(node => node.id)).toContain("brand");
  expect(JSON.stringify(model)).toBe(before);
});

it("derives the brand count from the snapshot instead of hardcoding 22", () => {
  const many = { ...model, candidates: [model.candidates[0], model.candidates[1], ...Array.from({ length: 22 }, (_, i) => node(`brand-${i}`, `提升 Brand${i} 项目盈利能力`, "profit"))] };
  const tree = buildGoalHierarchyTree(many, "zh");
  expect(tree.pages.profit.items.map(node => node.name)).toEqual(["品牌项目（22）"]);
  expect(projectGoalFocus(many, tree, "profit", "hierarchy").entities).toHaveLength(3);
});

it("does not fabricate context from evidence or hierarchy", () => {
  const result = projectGoalFocus(model, buildGoalHierarchyTree(model, "zh"), "brand", "context");
  expect(result.hasContext).toBe(false);
  expect(result.edges).toEqual([]);
  expect(result.entities.some(node => node.id.includes("C-source"))).toBe(false);
});

it("shows six typed endpoints using only the nine actual semantic relations", () => {
  const types = ["capability", "driver", "risk", "metric", "constraint", "un"];
  const names = ["advances", "drives", "amplifies", "blocks", "enables", "serves", "constrains", "measures", "sets"];
  const contextual = { ...model, relations: [...names.map((relationship, i) => ({ id: String(i), source: types[i % types.length], target: "brand", relationship, status: "confirmed" })), { id: "evidence", source: "C-source", target: "brand", relationship: "evidence" }] } as GoalModelView;
  const result = projectGoalFocus(contextual, buildGoalHierarchyTree(contextual, "zh"), "brand", "context");
  expect(result.hasContext).toBe(true);
  expect(result.edges.map(edge => edge.relationship)).toEqual(names);
  expect(new Set(result.entities.map(node => node.type))).toEqual(new Set(["goal", "capability", "driver", "risk", "metric", "constraint"]));
  expect(result.positions?.driver.x).toBeLessThan(result.positions!.brand.x);
  expect(result.positions?.risk.x).toBeGreaterThan(result.positions!.brand.x);
  expect(result.positions?.metric.y).toBeGreaterThan(result.positions!.brand.y);
});
