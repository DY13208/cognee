import type { CogneeInstance } from "@/modules/instances/types";
import { generateSopProposal } from "./sopClient";

test("posts the raw mind-map fields to the proposal endpoint", async () => {
  const fetch = jest.fn(async () => ({ ok: true, json: async () => ({ title: "草案" }) }) as Response);
  const instance = { name: "test", instanceId: "test", fetch } as CogneeInstance;
  const mindmapContext = { target: { text: "P：制定项目利润目标" } };

  const proposal = await generateSopProposal(instance, {
    datasetId: "dataset-1",
    roomKey: "room-rujw4n4j",
    nodeUid: "e1bd00ff-1f82-4a95-946e-7da665876c91",
    sourceUids: ["e1bd00ff-1f82-4a95-946e-7da665876c91"],
    mindmapContext,
  });

  expect(proposal.title).toBe("草案");
  expect(fetch).toHaveBeenCalledWith("/v1/teleology/sop/proposals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      dataset_id: "dataset-1",
      room_key: "room-rujw4n4j",
      node_uid: "e1bd00ff-1f82-4a95-946e-7da665876c91",
      source_uids: ["e1bd00ff-1f82-4a95-946e-7da665876c91"],
      mindmap_context: mindmapContext,
    }),
  });
});
