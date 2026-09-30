import type { CogneeInstance } from "@/modules/instances/types";

export interface SopSourceRequest {
  datasetId: string;
  roomKey: string;
  nodeUid: string;
  sourceUids?: string[];
  mindmapContext: Record<string, unknown>;
}

async function readError(resp: Response): Promise<string> {
  const err = await resp.json().catch(() => ({ detail: resp.statusText }));
  if (typeof err.detail === "string" && err.detail) return err.detail;
  if (typeof err.error === "string" && err.error) return err.error;
  return `Request failed: ${resp.status}`;
}

/** Thin adapter over the existing proposal endpoint. It does not write an SOP. */
export async function generateSopProposal(
  instance: CogneeInstance,
  source: SopSourceRequest,
): Promise<Record<string, unknown>> {
  const resp = await instance.fetch("/v1/teleology/sop/proposals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      dataset_id: source.datasetId,
      room_key: source.roomKey,
      node_uid: source.nodeUid,
      source_uids: source.sourceUids ?? [],
      mindmap_context: source.mindmapContext,
    }),
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}
