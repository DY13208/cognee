import { render, screen } from "@testing-library/react";
import type { GraphNodeSummary, ProposalItem, TeleologyProposal } from "@/modules/teleology/teleologyApi";
import type { OntologyEdge } from "./types";
import NavPanel from "./NavPanel";
import TeleologyFocusMap, { shouldShowFocusDetail } from "./TeleologyFocusMap";

const goal: GraphNodeSummary = { id: "goal-1", name: "Arencia项目利润", type: "Goal", description: "", child_count: 1 };
const purpose: GraphNodeSummary = { id: "purpose-1", name: "提高利润核算准确性", type: "Purpose", description: "" };
const candidatePurpose: ProposalItem = { id: "candidate-purpose", kind: "purpose", name: "提升利润透明度", description: "", confidence: 0.91, reason: "项目数据可核对", evidence_node_ids: ["document-1"], source_goal_ids: [goal.id], status: "proposed" };
const candidateRelation: ProposalItem = { id: "candidate-relation", kind: "relation", name: "", description: "", confidence: 0.85, reason: "文档证明贡献", evidence_node_ids: ["document-1"], source_goal_ids: [goal.id], source: goal.id, target: "other-goal", relationship: "advances", status: "proposed" };
const confirmedRelation: OntologyEdge = { id: "relation-1", sourceId: goal.id, targetId: "other-goal", sourceName: goal.name, targetName: "项目增长", sourceType: "Goal", targetType: "Goal", relationship: "serves" };

function proposal(items: ProposalItem[]): TeleologyProposal {
  return { id: "proposal-1", dataset_id: "dataset-1", source_goal_id: goal.id, status: "open", run_id: "run-1", created_at: 0, generated_by: "purpose-agent", summary: { purposes: 0, goals: 0, constraints: 0, serves: 0, advances: 0, blocks: 0, missing_purpose: 0 }, items };
}

function view({ purposes = [], relations = [], candidate = null }: { purposes?: GraphNodeSummary[]; relations?: OntologyEdge[]; candidate?: TeleologyProposal | null } = {}) {
  return render(<TeleologyFocusMap goal={goal} purposes={purposes} constraints={[]} relations={relations} proposal={candidate} subgoals={[]} childTotal={0} language="zh" onSelectProposal={jest.fn()} onSelectGoal={jest.fn()} />);
}

test("case 1: zero confirmed and zero proposal has a normal empty state", () => {
  view();
  expect(screen.getByText("暂无已确认的目的关系")).toBeInTheDocument();
  expect(screen.getByText("尚无目的推断")).toBeInTheDocument();
});

test("case 2: open Purpose appears in WHY", () => {
  view({ candidate: proposal([candidatePurpose]) });
  expect(screen.getByText(/待确认的目的建议/)).toBeInTheDocument();
  expect(screen.getByText("提升利润透明度")).toBeInTheDocument();
  expect(screen.queryByText("尚无目的推断")).not.toBeInTheDocument();
});

test("case 3: proposal relation is dashed and labeled", () => {
  const { container } = view({ candidate: proposal([candidateRelation]) });
  expect(container.querySelector(".teleology-relation-item.is-proposed")).toBeInTheDocument();
  expect(screen.getAllByText("AI建议").length).toBeGreaterThan(0);
});

test("case 4: confirmed relation uses a solid style", () => {
  const { container } = view({ relations: [confirmedRelation] });
  expect(container.querySelector(".teleology-relation-item.is-confirmed")).toBeInTheDocument();
  expect(screen.getByText("1 已确认 · 0 AI建议")).toBeInTheDocument();
});

test("case 5: confirmed and proposed layers coexist", () => {
  const { container } = view({ purposes: [purpose], relations: [confirmedRelation], candidate: proposal([candidatePurpose, candidateRelation]) });
  expect(container.querySelectorAll(".teleology-semantic-card.is-confirmed")).toHaveLength(1);
  expect(container.querySelectorAll(".teleology-semantic-card.is-proposed")).toHaveLength(1);
  expect(container.querySelectorAll(".teleology-relation-item")).toHaveLength(2);
});

test("case 6: a single node stays on the canvas; focus view is only the selected-node detail", () => {
  expect(shouldShowFocusDetail(null)).toBe(false);
  expect(shouldShowFocusDetail("goal-1")).toBe(true);
  const { container } = view();
  expect(container.querySelectorAll(".teleology-current-goal")).toHaveLength(1);
});

test("case 7: deep goal navigation uses indentation without repeated child labels", () => {
  const root = { ...goal, name: "公司" };
  const child = { ...goal, id: "child", name: "部门" };
  const grandchild = { ...goal, id: "grandchild", name: "项目" };
  const confirmed = { ...goal, id: "confirmed", name: "已确认目标", confirmed_count: 2 };
  render(<NavPanel language="zh" roots={[root, confirmed]} pages={{ [root.id]: { items: [child], total: 1, loading: false, loaded: true }, [child.id]: { items: [grandchild], total: 1, loading: false, loaded: true } }} focusId={grandchild.id} pathIds={[root.id, child.id, grandchild.id]} loading={false} statuses={{ [root.id]: "AI建议 2", [child.id]: "已确认 1" }} onPick={jest.fn()} onExpand={jest.fn()} onSearch={async () => []} />);
  expect(screen.getByText("AI建议 2")).toBeInTheDocument();
  expect(screen.getByText("已确认 2")).toBeInTheDocument();
  expect(screen.getByText("项目")).toBeInTheDocument();
  expect(screen.queryByText("下级")).not.toBeInTheDocument();
});
