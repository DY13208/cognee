import type { CogneeInstance } from "@/modules/instances/types";
import { reviewGoalCandidate } from "@/modules/teleology/teleologyApi";

export async function confirmGoalCandidates(
  instance: CogneeInstance,
  datasetId: string,
  candidateIds: string[],
  onProgress?: (completed: number) => void,
) {
  let confirmed = 0;
  const failed: { id: string; error: string }[] = [];
  for (const [index, id] of candidateIds.entries()) {
    try {
      await reviewGoalCandidate(instance, datasetId, id, "confirmed");
      confirmed += 1;
    } catch (cause) {
      failed.push({ id, error: cause instanceof Error ? cause.message : String(cause) });
    }
    onProgress?.(index + 1);
  }
  return { confirmed, failed };
}
