import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { CogneeInstance } from "@/modules/instances/types";
import { getGoalModel, reviewGoalCandidate, startTeleologyBuild } from "@/modules/teleology/teleologyApi";
import GoalModelPage from "./GoalModelPage";

jest.mock("@/modules/teleology/teleologyApi", () => ({
  getGoalModel: jest.fn(),
  startTeleologyBuild: jest.fn(),
  reviewGoalCandidate: jest.fn(),
}));

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
        { node_id: "project", name: "Arencia项目", source_class: "Project" },
        { node_id: "metric", name: "项目利润分", source_class: "Metric" },
      ],
      parent_candidate_id: null,
      status: "proposed" as const,
      run_id: "run-1",
      generated_by: "dataset_goal_build",
      semantic_hash: "abc",
    },
    {
      id: "accuracy",
      dataset_id: "ds-1",
      name: "提高 Arencia 项目利润核算准确性",
      description: "更具体的核算结果。",
      confidence: 0.68,
      reason: "核算指标把盈利结果收窄。",
      source_node_ids: ["project", "accuracy"],
      evidence: [{ node_id: "accuracy", name: "Arencia利润核算准确性指标", source_class: "Metric" }],
      parent_candidate_id: "profit",
      status: "proposed" as const,
      run_id: "run-1",
      generated_by: "dataset_goal_build",
      semantic_hash: "def",
    },
  ],
  hierarchy: [
    { id: "profit", name: "提升 Arencia 项目盈利能力", parent_candidate_id: null, status: "proposed", confidence: 0.72, evidence_count: 2 },
    { id: "accuracy", name: "提高 Arencia 项目利润核算准确性", parent_candidate_id: "profit", status: "proposed", confidence: 0.68, evidence_count: 1 },
  ],
  purposes: [{ id: "p1", kind: "purpose", name: "实现盈利", status: "proposed", reason: "来自证据", confidence: 0.7, evidence: [], source_node_ids: ["project"], goal_id: "profit" }],
  constraints: [],
  relations: [{ id: "r1", kind: "relation", name: "advances", relationship: "advances", status: "proposed", reason: "更具体的结果推进上一级。", confidence: 0.64, evidence: [], source_node_ids: ["accuracy"], goal_id: "accuracy", source: "accuracy", target: "profit" }],
  classifications: [
    { id: "resp", name: "责任分工", source_class: "Responsibility", layer: "company_tree" },
    { id: "project", name: "Arencia项目", source_class: "Project", layer: "company_tree" },
    { id: "metric", name: "项目利润分", source_class: "Metric", layer: "company_tree" },
  ],
};

const instance = { name: "test", instanceId: "test", fetch: jest.fn() } as CogneeInstance;

describe("GoalModelPage", () => {
  beforeEach(() => {
    jest.mocked(getGoalModel).mockResolvedValue(model);
    jest.mocked(startTeleologyBuild).mockResolvedValue(model);
    jest.mocked(reviewGoalCandidate).mockResolvedValue({ graph_committed: false, committed: false });
  });

  it("shows the AI goal hierarchy and keeps the company tree in the source panel", async () => {
    render(<GoalModelPage instance={instance} datasetId="ds-1" datasetName="yiran_cpd" language="zh" />);

    expect(await screen.findByRole("button", { name: /提升 Arencia 项目盈利能力/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /提高 Arencia 项目利润核算准确性/ })).toBeTruthy();
    expect(screen.getByText("提案 · 72% · 2 证据")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "责任分工" })).toBeNull();
    const sources = screen.getByRole("complementary", { name: "来源 / Company Tree" });
    expect(sources).toHaveTextContent("责任分工");
    expect(sources).toHaveTextContent("Responsibility");
    expect(screen.getByText("来自证据")).toBeTruthy();
  });

  it("reviews a goal without committing the graph", async () => {
    render(<GoalModelPage instance={instance} datasetId="ds-1" language="zh" />);
    fireEvent.click(await screen.findByRole("button", { name: "标为已确认" }));

    await waitFor(() => expect(reviewGoalCandidate).toHaveBeenCalledWith(instance, "ds-1", "profit", "confirmed"));
    expect(startTeleologyBuild).not.toHaveBeenCalled();
  });
});
