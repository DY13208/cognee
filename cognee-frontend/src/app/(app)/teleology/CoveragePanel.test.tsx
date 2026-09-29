import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { CogneeInstance } from "@/modules/instances/types";
import { commitCoverageRun, getCoverageRun } from "@/modules/teleology/teleologyApi";
import CoveragePanel from "./CoveragePanel";

jest.mock("@/modules/teleology/teleologyApi", () => ({
  getCoverageState: jest.fn(async () => ({ items: [], total: 0, summary: {} })),
  getCoverageRun: jest.fn(),
  commitCoverageRun: jest.fn(),
  startCoverageRun: jest.fn(),
  coverageAction: jest.fn(),
}));

const preview = {
  run_id: "run-1",
  dry_run: true,
  proposals_total: 10,
  proposals_committable: 2,
  empty_proposals: 8,
  conflict_proposals: 0,
  stale_proposals: [],
  items_total: 15,
  purpose_count: 12,
  constraint_count: 2,
  goal_count: 1,
  serves_count: 0,
  advances_count: 0,
  blocks_count: 0,
  proposal_details: [],
  committed_proposals: [],
  failed_proposals: [],
  skipped_empty: ["empty"],
  already_committed: [],
  committed_nodes: 0,
  committed_relations: 0,
  skipped_items: 0,
};

const instance = { name: "test", instanceId: "test", fetch: jest.fn() } as CogneeInstance;

beforeEach(() => {
  jest.mocked(getCoverageRun).mockResolvedValue({
    id: "run-1",
    dataset_id: "dataset-1",
    status: "completed",
    mode: "incremental",
    batch_size: 20,
    concurrency: 3,
    total_goals: 1,
    eligible_goals: 1,
    queued_goals: 0,
    processed_goals: 1,
    skipped_goals: 0,
    proposal_goals: 1,
    no_change_goals: 0,
    no_context_goals: 0,
    failed_goals: 0,
  });
  jest.mocked(commitCoverageRun).mockImplementation(async (_client, _datasetId, _runId, dryRun) => (
    dryRun ? preview : { ...preview, dry_run: false, committed_proposals: ["p1", "p2"], committed_nodes: 15 }
  ));
});

test("confirms a reviewed coverage run only after a dry-run preview", async () => {
  render(<CoveragePanel instance={instance} datasetId="dataset-1" onClose={jest.fn()} />);
  fireEvent.change(screen.getByLabelText(/已人工验收的 Coverage Run/), { target: { value: "run-1" } });
  fireEvent.click(screen.getByRole("button", { name: "一键确认本次 AI 建议" }));

  const dialog = await screen.findByRole("dialog", { name: "确认本次 AI 建议" });
  expect(within(dialog).getByText("12 个 Purpose")).toBeInTheDocument();
  expect(within(dialog).getByText("2 个 Constraint")).toBeInTheDocument();
  expect(within(dialog).getByText("1 个 Suggested Goal")).toBeInTheDocument();
  expect(within(dialog).getByText("8 个空 Proposal 将跳过")).toBeInTheDocument();
  expect(jest.mocked(commitCoverageRun)).toHaveBeenCalledTimes(1);
  expect(jest.mocked(commitCoverageRun).mock.calls[0][3]).toBe(true);

  fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(jest.mocked(commitCoverageRun)).toHaveBeenCalledTimes(1);

  fireEvent.click(screen.getByRole("button", { name: "一键确认本次 AI 建议" }));
  const confirm = await screen.findByRole("dialog", { name: "确认本次 AI 建议" });
  fireEvent.click(within(confirm).getByRole("button", { name: "确认全部写入" }));
  await waitFor(() => expect(jest.mocked(commitCoverageRun)).toHaveBeenCalledTimes(3));
  expect(jest.mocked(commitCoverageRun).mock.calls[2][3]).toBe(false);
  expect(await screen.findByRole("status")).toHaveTextContent("已提交 2 个 Proposal");
});
