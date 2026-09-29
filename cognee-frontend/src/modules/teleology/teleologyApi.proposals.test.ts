import type { CogneeInstance } from "@/modules/instances/types";
import { commitCoverageRun, getLatestOpenGoalProposal, getTeleologyProposal, listTeleologyProposals } from "./teleologyApi";

function instance(payload: unknown) {
  const fetch = jest.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    expect(input).toBeTruthy();
    return { ok: true, json: async () => payload } as Response;
  });
  return { client: { name: "test", instanceId: "test", fetch } as CogneeInstance, fetch };
}

test("lists open proposals for the selected dataset and source goal", async () => {
  const { client, fetch } = instance({ items: [{ id: "proposal-1", source_goal_id: "goal-1", status: "open", generated_by: "purpose-agent", items_count: 2 }], total: 1 });
  const result = await listTeleologyProposals(client, "dataset-1", { sourceGoalId: "goal-1", status: "open" });
  expect(result.items[0].id).toBe("proposal-1");
  expect(String(fetch.mock.calls[0][0])).toContain("source_goal_id=goal-1");
  expect(String(fetch.mock.calls[0][0])).toContain("status=open");
});

test("normalizes the production review detail shape for the existing review UI", async () => {
  const { client, fetch } = instance({
    id: "proposal-1", dataset_id: "dataset-1", source_goal_id: "goal-1", status: "open", generated_by: "purpose-agent", run_id: "run-1",
    items: [{ id: "item-1", kind: "purpose", name: "Improve margin", review_status: "proposed", evidence: [{ id: "document-1", name: "Decision", type: "Document" }] }],
  });
  const detail = await getTeleologyProposal(client, "dataset-1", "proposal-1");
  expect(detail.items[0].status).toBe("proposed");
  expect(detail.summary.purposes).toBe(1);
  expect(detail.items[0].evidence?.[0].type).toBe("Document");
  expect(String(fetch.mock.calls[0][0])).toContain("dataset_id=dataset-1");
});

test("loads the newest purpose-agent proposal before other open proposals", async () => {
  const fetch = jest.fn(async (input: RequestInfo | URL) => ({
    ok: true,
    json: async () => String(input).includes("generated_by=purpose-agent")
      ? { items: [{ id: "agent-proposal", generated_by: "purpose-agent" }], total: 1 }
      : { id: "agent-proposal", items: [], status: "open" },
  } as Response));
  const client = { name: "test", instanceId: "test", fetch } as CogneeInstance;
  const loaded = await getLatestOpenGoalProposal(client, "dataset-1", "goal-1");
  expect(loaded?.id).toBe("agent-proposal");
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(String(fetch.mock.calls[0][0])).toContain("generated_by=purpose-agent");
});

test("previews one coverage run before committing it", async () => {
  const { client, fetch } = instance({ proposals_committable: 1, purpose_count: 12 });
  await commitCoverageRun(client, "dataset-1", "run/1", true);
  await commitCoverageRun(client, "dataset-1", "run/1", false);
  expect(String(fetch.mock.calls[0][0])).toBe("/v1/teleology/coverage/runs/run%2F1/commit-all");
  expect(fetch.mock.calls[0][1]).toMatchObject({
    method: "POST",
    body: JSON.stringify({ dataset_id: "dataset-1", dry_run: true }),
  });
  expect(fetch.mock.calls[1][1]).toMatchObject({
    body: JSON.stringify({ dataset_id: "dataset-1", dry_run: false }),
  });
});
