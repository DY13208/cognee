import type { CogneeInstance } from "@/modules/instances/types";
import { reviewGoalCandidate } from "@/modules/teleology/teleologyApi";
import { confirmGoalCandidates } from "./confirmGoalCandidates";

jest.mock("@/modules/teleology/teleologyApi", () => ({ reviewGoalCandidate: jest.fn() }));

it("continues after one review fails and reports partial success", async () => {
  const instance = { fetch: jest.fn() } as unknown as CogneeInstance;
  const progress: number[] = [];
  jest.mocked(reviewGoalCandidate)
    .mockResolvedValueOnce({ graph_committed: false, committed: false })
    .mockRejectedValueOnce(new Error("Review item not found"))
    .mockResolvedValueOnce({ graph_committed: false, committed: false });

  const result = await confirmGoalCandidates(instance, "dataset-1", ["a", "b", "c"], (count) => progress.push(count));

  expect(result).toEqual({ confirmed: 2, failed: [{ id: "b", error: "Review item not found" }] });
  expect(progress).toEqual([1, 2, 3]);
  expect(reviewGoalCandidate).toHaveBeenNthCalledWith(3, instance, "dataset-1", "c", "confirmed");
});
