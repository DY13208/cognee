import { buildDerivedGoalTree, isCurrentGoal, isMissingGraphGoal, parseDataNodeId, resolveFocusTarget } from "./derivedGoalTree";
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

  it("keeps historical confirmed goals out of the current tree and pending count", () => {
    const historical = {
      ...model.candidates[0],
      id: "historical",
      name: "历史已确认目标",
      status: "confirmed" as const,
      outside_current_snapshot: true,
    };
    const legacy = {
      ...model.candidates[0],
      id: "legacy",
      name: "旧状态历史目标",
      status: "legacy_confirmed" as const,
    };
    const current = buildDerivedGoalTree({ ...model, candidates: [...model.candidates, historical, legacy] }, "zh");
    expect(current.roots.map((goal) => goal.id)).toEqual(["profit"]);
    expect(current.byId.has("historical")).toBe(false);
    expect(current.byId.has("legacy")).toBe(false);
    expect(current.statuses.historical).toBeUndefined();
    expect(current.statuses.legacy).toBeUndefined();
    expect(current.statuses.accuracy).toBe("待确认");
    expect([...model.candidates, historical, legacy].filter((goal) => isCurrentGoal(goal) && goal.status === "proposed").map((goal) => goal.id)).toEqual(["accuracy"]);
  });

  it("connects data nodes so they serve the derived goal", () => {
    const focus = tree.focus("profit");
    expect(focus?.relations.map((edge) => [edge.sourceName, edge.relationship, edge.targetName])).toEqual([
      ["Arencia项目", "evidence", "提升 Arencia 项目盈利能力"],
      ["项目利润分", "evidence", "提升 Arencia 项目盈利能力"],
    ]);
    expect(focus?.goal.child_count).toBe(1);
    expect(focus?.relations.every((edge) => edge.relationship !== "serves")).toBe(true);
    expect(focus?.children.map((child) => child.candidate_id)).toEqual(["accuracy"]);
    expect(parseDataNodeId(focus!.relations[0].sourceId)).toEqual({ goalId: "profit", nodeId: "project" });
  });

  it("keeps the snapshot candidate id apart from the visual id", () => {
    const root = tree.byId.get("profit");
    expect(root?.candidate_id).toBe("profit");
    expect(root?.id).toBe("profit");
    expect(root?.visual_id).toBe("visual:profit");
    expect(root?.graph_id).toBeNull();
    expect(resolveFocusTarget(tree, "visual:profit")).toEqual({
      candidateId: "profit",
      graphId: null,
      visualId: "visual:profit",
    });
    expect(resolveFocusTarget(tree, "data:profit:project").candidateId).toBe("profit");
    expect(resolveFocusTarget(tree, "data:profit:project").graphId).toBeNull();
    expect(resolveFocusTarget(tree, "project")).toEqual({
      candidateId: "profit",
      graphId: null,
      visualId: "visual:profit",
    });
    expect(tree.path("profit")).toHaveLength(1);
    expect(isMissingGraphGoal("'Goal not found in dataset graph'")).toBe(true);
  });

  it("resolves the canonical root from the snapshot without a graph id", () => {
    const rootId = "f873e41a-99cb-590e-aace-ef1531c2e964";
    const names = [
      "提升公司整体经营利润",
      "保障财务健康与资金安全",
      "提升组织能力与人才健康度",
      "保障经营合规与风险可控",
      "提升 AI 与知识资产能力",
    ];
    const root = buildDerivedGoalTree({
      ...model,
      candidates: [
        {
          ...model.candidates[0],
          id: rootId,
          name: "实现公司长期可持续经营与利润最大化",
          parent_candidate_id: null,
          graph_id: null,
          source_node_ids: ["4ad0b6f7-83b6-5fa2-8ab3-50fa89300cdc"],
          evidence: [{ node_id: "4ad0b6f7-83b6-5fa2-8ab3-50fa89300cdc", name: "公司树节点", source_class: "Other" }],
        },
        ...names.map((name, index) => ({
          ...model.candidates[1],
          id: `child-${index}`,
          name,
          parent_candidate_id: rootId,
          evidence: [],
          source_node_ids: [],
        })),
      ],
    }, "zh");
    const focus = root.focus(rootId);
    expect(root.path(rootId)).toHaveLength(1);
    expect(focus?.goal.candidate_id).toBe(rootId);
    expect(focus?.goal.id).toBe(rootId);
    expect(focus?.goal.graph_id).toBeNull();
    expect(focus?.goal.child_count).toBe(names.length);
    expect(focus?.children.map((child) => child.name)).toEqual(names);
    expect(focus?.relations.map((edge) => edge.relationship)).toEqual(["evidence"]);
    expect(root.byId.get("data:f873e41a-99cb-590e-aace-ef1531c2e964:4ad0b6f7-83b6-5fa2-8ab3-50fa89300cdc")?.type).toBe("Data");
    expect(resolveFocusTarget(root, "4ad0b6f7-83b6-5fa2-8ab3-50fa89300cdc")).toEqual({
      candidateId: rootId,
      graphId: null,
      visualId: `visual:${rootId}`,
    });
    expect(resolveFocusTarget(root, `visual:${rootId}`).candidateId).toBe(rootId);
  });

  it("keeps a leaf goal's evidence out of its child count", () => {
    const un = buildDerivedGoalTree({
      ...model,
      candidates: [{
        ...model.candidates[0],
        id: "un",
        name: "提升 UNOVE(UN) 项目盈利能力",
        parent_candidate_id: "profit",
        evidence: [
          { node_id: "un-profit", name: "陈华俊 C:UN项目利润分", source_class: "Metric" },
          { node_id: "channel", name: "渠道增长", source_class: "Other" },
          { node_id: "fee", name: "退后费比15%-20%", source_class: "Other" },
          { node_id: "rule", name: "渠道统计规则", source_class: "Other" },
        ],
        source_node_ids: ["un-profit", "channel", "fee", "rule"],
      }],
    }, "zh");
    const focus = un.focus("un");
    expect(focus?.children).toEqual([]);
    expect(focus?.goal.child_count).toBe(0);
    expect(focus?.relations.map((edge) => edge.relationship)).toEqual(["evidence", "evidence", "evidence", "evidence"]);
    expect(focus?.relations.map((edge) => edge.sourceType)).toEqual(["Data", "Data", "Data", "Data"]);
  });

  it("counts chevrons from hierarchy parents, including when only hierarchy carries the link", () => {
    const rows: Array<[string, string | null]> = [
      ["root", null],
      ["g_profit", "root"],
      ["g_finance", "root"],
      ["g_org", "root"],
      ["g_compliance", "root"],
      ["g_ai", "root"],
      ["g_mainbusiness", "g_profit"],
      ["g_efficiency", "g_profit"],
      ["g_growth", "g_profit"],
      ["g_profit_leaf", "g_profit"],
      ["g_brandprofit", "g_mainbusiness"],
      ["g_main_leaf", "g_mainbusiness"],
      ["brand-1", "g_brandprofit"],
      ["brand-2", "g_brandprofit"],
      ["brand-3", "g_brandprofit"],
      ["brand-4", "g_brandprofit"],
      ["eff-1", "g_efficiency"],
      ["eff-2", "g_efficiency"],
      ["eff-3", "g_efficiency"],
      ["eff-4", "g_efficiency"],
      ["grow-1", "g_growth"],
      ["grow-2", "g_growth"],
      ["grow-3", "g_growth"],
      ["grow-4", "g_growth"],
      ["comp-1", "g_compliance"],
      ["comp-2", "g_compliance"],
      ["comp-3", "g_compliance"],
    ];
    const historical = Array.from({ length: 8 }, (_, index) => ({
      ...model.candidates[0],
      id: `historical-${index}`,
      name: index === 0 ? "root" : `历史目标 ${index}`,
      parent_candidate_id: null,
      status: "legacy_confirmed" as const,
      outside_current_snapshot: true,
      evidence: [],
      source_node_ids: [`historical-source-${index}`],
    }));
    expect(rows).toHaveLength(27);
    expect(rows.length + historical.length).toBe(35);
    const tree = buildDerivedGoalTree({
      ...model,
      candidates: [...rows.map(([id]) => ({
        ...model.candidates[0],
        id,
        name: id,
        parent_candidate_id: null,
        evidence: id === "g_profit" ? [{ node_id: "profit-score", name: "公司利润分", source_class: "Metric" }] : [],
        source_node_ids: [],
      })), ...historical],
      hierarchy: rows.map(([id, parent]) => ({
        id,
        name: id,
        parent_candidate_id: parent,
        status: "proposed",
        confidence: 1,
        evidence_count: 0,
      })),
    }, "zh");
    expect(tree.byId.size).toBe(28); // 27 goals plus one evidence Data node.
    expect(tree.roots.map((goal) => goal.id)).toEqual(["root"]);
    expect(tree.search("历史目标")).toEqual([]);
    expect(tree.search("root").map((goal) => goal.id)).toEqual(["root"]);
    for (const goal of historical) {
      expect(tree.byId.has(goal.id)).toBe(false);
      expect(tree.sourceOwners.has(goal.source_node_ids[0])).toBe(false);
      expect(tree.focus(goal.id)).toBeNull();
    }
    expect(tree.byId.get("root")?.child_count).toBe(5);
    expect(tree.byId.get("g_profit")?.child_count).toBe(4);
    expect(tree.byId.get("g_mainbusiness")?.child_count).toBe(2);
    expect(tree.byId.get("g_brandprofit")?.child_count).toBe(4);
    expect(tree.byId.get("g_efficiency")?.child_count).toBe(4);
    expect(tree.byId.get("g_growth")?.child_count).toBe(4);
    expect(tree.byId.get("g_compliance")?.child_count).toBe(3);
    expect(tree.byId.get("g_profit_leaf")?.child_count).toBe(0);
    expect(tree.focus("g_profit")?.relations.map((edge) => edge.relationship)).toEqual(["evidence"]);
  });
});
