import type { GraphNodeSummary, ProposalItem, TeleologyProposal } from "@/modules/teleology/teleologyApi";
import { buildPurposeNeighborhood } from "./purposeCanvas";
import type { OntologyEdge } from "./types";

const focus: GraphNodeSummary = { id: "goal-1", name: "Arencia项目利润", type: "Goal", description: "", child_count: 1 };
const purpose: GraphNodeSummary = { id: "purpose-1", name: "提高利润核算准确性", type: "Purpose", description: "" };
const constraint: GraphNodeSummary = { id: "constraint-1", name: "不得提前确认收入", type: "Constraint", description: "" };
const child: GraphNodeSummary = { id: "child-1", name: "月度核算", type: "Goal", description: "", child_count: 0 };
const confirmed: OntologyEdge = {
  id: "relation-1",
  sourceId: "other-goal",
  targetId: focus.id,
  sourceName: "项目增长",
  targetName: focus.name,
  sourceType: "Goal",
  targetType: "Goal",
  relationship: "serves",
};
const candidatePurpose: ProposalItem = {
  id: "candidate-purpose",
  kind: "purpose",
  name: "提升利润透明度",
  description: "",
  confidence: 0.91,
  reason: "项目数据可核对",
  evidence_node_ids: ["document-1"],
  source_goal_ids: [focus.id],
  status: "proposed",
};
const candidateRelation: ProposalItem = {
  id: "candidate-relation",
  kind: "relation",
  name: "",
  description: "",
  confidence: 0.85,
  reason: "文档证明贡献",
  evidence_node_ids: ["document-1"],
  source_goal_ids: [focus.id],
  source: focus.id,
  target: "other-goal",
  relationship: "advances",
  status: "proposed",
};

function proposal(items: ProposalItem[]): TeleologyProposal {
  return {
    id: "proposal-1",
    dataset_id: "dataset-1",
    source_goal_id: focus.id,
    status: "open",
    run_id: "run-1",
    created_at: 0,
    generated_by: "purpose-agent",
    summary: { purposes: 0, goals: 0, constraints: 0, serves: 0, advances: 0, blocks: 0, missing_purpose: 0 },
    items,
  };
}

test("evidence stays data and is not a goal or a serves edge", () => {
  const evidence: OntologyEdge = {
    id: "evidence-1",
    sourceId: "metric-1",
    targetId: focus.id,
    sourceName: "陈华俊 C:UN项目利润分",
    targetName: focus.name,
    sourceType: "Data",
    targetType: "Goal",
    relationship: "evidence",
  };
  const neighborhood = buildPurposeNeighborhood({
    focus: { ...focus, child_count: 0 },
    purposes: [],
    constraints: [],
    relations: [evidence],
    proposal: null,
    children: [],
  });
  const source = neighborhood.entities.find((entity) => entity.id === "metric-1");
  expect(source?.kind).not.toBe("Goal");
  expect(source?.type).toBe("Data");
  expect(source?.childCount).toBe(0);
  expect(neighborhood.entities.find((entity) => entity.id === focus.id)?.childCount).toBe(0);
  expect(neighborhood.edges.map((edge) => edge.relationship)).toEqual(["evidence"]);
});

test("a goal with no relations still stays on the canvas", () => {
  const neighborhood = buildPurposeNeighborhood({ focus, purposes: [], constraints: [], relations: [], proposal: null, children: [] });
  expect(neighborhood.entities.map((entity) => entity.id)).toEqual([focus.id]);
  expect(neighborhood.edges).toHaveLength(0);
});

test("confirmed purpose and constraint sit upstream of the goal", () => {
  const neighborhood = buildPurposeNeighborhood({ focus, purposes: [purpose], constraints: [constraint], relations: [], proposal: null, children: [child] });
  expect(neighborhood.entities.find((entity) => entity.id === purpose.id)?.kind).toBe("Purpose");
  expect(neighborhood.entities.find((entity) => entity.id === constraint.id)?.reviewStatus).toBe("confirmed");
  expect(neighborhood.edges.find((edge) => edge.relationship === "purpose")).toMatchObject({ sourceId: purpose.id, targetId: focus.id, status: "confirmed" });
  expect(neighborhood.edges.find((edge) => edge.relationship === "constrains")?.status).toBe("confirmed");
  expect(neighborhood.edges.find((edge) => edge.relationship === "has_subgoal")).toMatchObject({ sourceId: focus.id, targetId: child.id });
});

test("proposal nodes and relations stay dashed and do not replace confirmed edges", () => {
  const neighborhood = buildPurposeNeighborhood({
    focus,
    purposes: [purpose],
    constraints: [],
    relations: [confirmed],
    proposal: proposal([candidatePurpose, candidateRelation]),
    children: [],
  });
  expect(neighborhood.entities.find((entity) => entity.id === candidatePurpose.id)?.reviewStatus).toBe("proposed");
  expect(neighborhood.edges.find((edge) => edge.id === "relation-1")?.status).toBe("confirmed");
  expect(neighborhood.edges.find((edge) => edge.id === "proposal-rel|candidate-relation")).toMatchObject({
    sourceId: focus.id,
    targetId: "other-goal",
    relationship: "advances",
    status: "proposed",
  });
});
