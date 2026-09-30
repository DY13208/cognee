import { buildSopMermaid, buildSopViewModel } from "./sopViewModel";

const REAL_UID = "e1bd00ff-1f82-4a95-946e-7da665876c91";
const REAL_ID = "e7f37cf4-fda6-5856-93e2-c688fc0a1352";

const proposal = {
  title: "制定项目利润目标 SOP 草案",
  objective: "提升项目利润",
  scope: "room-rujw4n4j",
  goal: { id: "goal-profit", name: "提升项目利润" },
  dataset_id: "dd3aa689-ec26-5887-9730-310eec869d1c",
  run_id: "f7d609ae-4e88-4e4f-b8b3-523e92246bd4",
  overall_confidence: 0.72,
  status: "proposal",
  inputs: [{
    id: "I1",
    text: "利润测算模型",
    evidence_status: "SOURCE",
    source_uid: REAL_UID,
    evidence_node_id: REAL_ID,
  }],
  checks: [{
    id: "C1",
    text: "确认未发生被禁止的行为：删除原始记录",
    evidence_status: "DERIVED",
    reason: "由约束“禁止删除原始记录”推导验收项；约束本身不是执行步骤。",
    derived_from_constraint_id: "constraint-1",
  }],
  plan: [{
    id: "P1",
    text: "制定项目利润目标",
    evidence_status: "SOURCE",
    source_uid: REAL_UID,
    evidence_node_id: REAL_ID,
    reason: "节点名称明确以执行计划标记开头。",
  }],
  gaps: ["负责人", "缺少可验收的检查标准"],
  missing_details: [{ field: "负责人", evidence_status: "MISSING", reason: "当前资料未找到明确责任人" }],
  constraints: [{ id: "constraint-1", name: "禁止删除原始记录" }],
  risks: ["multiple goals share source provenance"],
  validation: {
    status: "NEEDS_REVIEW",
    unsupported_claims: [],
    quality_gaps: ["缺少可验收的检查标准"],
    missing_fields: ["负责人"],
    provenance_conflicts: [{ reason: "primary_goal provenance conflict" }],
  },
};

describe("SOP view model", () => {
  const view = buildSopViewModel(proposal);

  it("keeps the readable procedure and hides technical identifiers from the public fields", () => {
    const publicText = [
      view.title,
      view.objective,
      view.confidence,
      ...view.steps.flatMap((item) => [item.label, item.text, item.reason]),
      ...view.checks.flatMap((item) => [item.text, item.reason]),
      ...view.inputs.map((item) => item.text),
      ...view.missing.flatMap((item) => [item.field, item.reason]),
      ...view.basis,
      ...view.notices,
      ...view.flow.map((node) => node.text),
    ].join("\n");

    expect(view.steps[0].text).toBe("制定项目利润目标");
    expect(view.inputs[0].text).toBe("利润测算模型");
    expect(view.missing.map((item) => item.field)).toEqual(expect.arrayContaining(["负责人"]));
    expect(view.basis.join("\n")).toContain("节点名称明确以执行计划标记开头");
    expect(view.status).toBe("NEEDS_REVIEW");
    expect(publicText).not.toContain(REAL_UID);
    expect(publicText).not.toContain(REAL_ID);
    expect(publicText).not.toContain(proposal.run_id);
    expect(publicText).not.toContain("source_uid");
    expect(publicText).not.toContain("evidence_node_id");
    expect(publicText).not.toContain("run_id");
    expect(publicText).not.toContain("{");
    expect(view.mermaid).not.toContain(REAL_UID);
    expect(view.mermaid).not.toContain(proposal.run_id);
  });

  it("keeps identifiers and the mermaid source in the developer fold", () => {
    expect(view.developer.runId).toBe(proposal.run_id);
    expect(view.developer.items.find((item) => item.label === "P1")?.sourceUid).toBe(REAL_UID);
    expect(view.developer.items.find((item) => item.label === "P1")?.evidenceNodeId).toBe(REAL_ID);
    expect(view.mermaid).toContain("制定项目利润目标");
    expect(view.mermaid).toContain("flowchart TD");
    expect(view.mermaid).toBe(buildSopMermaid(view.flow));
    expect(view.mermaid).not.toContain(REAL_UID);
  });
});
