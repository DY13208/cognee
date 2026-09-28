import { CARD_H, CARD_W, layoutNeighborhood } from "./layoutDag";
import type { OntologyEdge, OntologyEntity } from "./types";

const ids = ["root", "a", "b", "shared", "metric", "document"];
const entities: OntologyEntity[] = ids.map((id) => ({ id, name: id, type: "Goal", kind: "Goal" }));
const connections: [string, string, string][] = [
  ["root", "a", "has_subgoal"], ["root", "b", "has_subgoal"],
  ["a", "shared", "has_subgoal"], ["b", "shared", "has_detail_reference"],
  ["metric", "root", "serves"], ["document", "root", "blocks"],
];
const edges: OntologyEdge[] = connections.map(([sourceId, targetId, relationship], index) => ({
  id: String(index), sourceId, targetId, relationship,
  sourceName: sourceId, targetName: targetId, sourceType: "Goal", targetType: "Goal",
}));

test("hierarchy cards do not overlap with shared goals and other relations", () => {
  const layout = layoutNeighborhood({ focusId: "root", entities, edges, viewMode: "hierarchy", canvasWidth: 800, hopDepth: 100 });
  expect(layout.nodes).toHaveLength(ids.length);
  for (let i = 0; i < layout.nodes.length; i += 1) {
    for (let j = i + 1; j < layout.nodes.length; j += 1) {
      const a = layout.nodes[i];
      const b = layout.nodes[j];
      const overlap = a.x < b.x + CARD_W && a.x + CARD_W > b.x && a.y < b.y + CARD_H && a.y + CARD_H > b.y;
      expect(overlap).toBe(false);
    }
  }
});
