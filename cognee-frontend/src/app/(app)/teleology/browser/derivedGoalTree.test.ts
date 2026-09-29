import { buildDerivedGoalTree, parseDataNodeId } from "./derivedGoalTree";
import type { GoalModelView } from "@/modules/teleology/teleologyApi";

const model = {
  dataset_id: "ds-1",
  run_id: "run-1",
  status: "completed",
  committed: false,
  graph_committed: false,
  candidates: [
    {
      id: "profit",
      dataset_id: "ds-1",
      name: "提升 Arencia 项目盈利能力",
      description: "由项目与利润指标综合得到的业务结果。",
      confidence: 0.72,
      reason: "项目与利润指标一起指向盈利结果。",
      source_node_ids: ["project", "metric"],
      evidence: [
        { node_id: "project", name: "Arencia项目", source_class: "Project", semantic_class: "Project" },
        { node_id: "metric", name: "项目利润分", source_class: "Metric", semantic_class: "Metric" },
      ],
      parent_candidate_id: null,
      status: "confirmed" as const,
      run_id: "run-1",
      generated_by: "dataset_goal_build",
      semantic_hash: "abc",
    },
    {
      id: "accuracy",
      dataset_id: "ds-1",
      name: "提高 Arencia 项目利润核算准确性",
      description: "",
      confidence: 0.6,
      reason: "",
      source_node_ids: ["doc"],
      evidence: [{ node_id: "doc", name: "年度利润目标文档", source_class: "Document", semantic_class: "Document" }],
      parent_candidate_id: "profit",
      status: "proposed" as const,
      run_id: "run-1",
      generated_by: "dataset_goal_build",
      semantic_hash: "def",
    },
    {
      id: "rejected-goal",
      dataset_id: "ds-1",
      name: "责任分工",
      description: "",
      confidence: 0.2,
      reason: "",
      source_node_ids: [],
      evidence: [],
      parent_candidate_id: null,
      status: "rejected" as const,
      run_id: "run-1",
      generated_by: "dataset_goal_build",
      semantic_hash: "ghi",
    },
  ],
  hierarchy: [],
  purposes: [],
  constraints: [],
  relations: [],
  classifications: [],
} as GoalModelView;

describe("derived goal tree", () => {
  const tree = buildDerivedGoalTree(model, "zh");

  it("shows derived goals as the subject and company-tree nodes as their data", () => {
    expect(tree.roots.map((goal) => goal.name)).toEqual(["提升 Arencia 项目盈利能力"]);
    expect(tree.roots.map((goal) => goal.name)).not.toContain("Arencia项目");
    expect(tree.roots.map((goal) => goal.name)).not.toContain("责任分工");
    const children = tree.pages.profit.items.map((item) => item.name);
    expect(children).toEqual(["提高 Arencia 项目利润核算准确性", "Arencia项目", "项目利润分"]);
    expect(tree.statuses.profit).toBe("已确认");
    expect(tree.statuses[tree.pages.profit.items[1].id]).toBe("数据 · 项目");
    expect(tree.statuses[tree.pages.profit.items[2].id]).toBe("数据 · 指标");
    expect(tree.statuses.accuracy).toBe("待确认");
  });

  it("connects data nodes so they serve the derived goal", () => {
    const focus = tree.focus("profit");
    expect(focus?.relations.map((edge) => [edge.sourceName, edge.relationship, edge.targetName])).toEqual([
      ["Arencia项目", "serves", "提升 Arencia 项目盈利能力"],
      ["项目利润分", "serves", "提升 Arencia 项目盈利能力"],
    ]);
    expect(parseDataNodeId(focus!.children[0].id)).toEqual({ goalId: "profit", nodeId: "project" });
  });
});
