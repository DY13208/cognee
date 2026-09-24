import type { LaidOutEdge, LaidOutNode, OntologyEdge, OntologyEntity, ViewMode } from "./types";

const CARD_W = 200;
const CARD_H = 80;
const COL_GAP = 120;
const ROW_GAP = 28;
const PAD_X = 48;
const PAD_Y = 48;

export { CARD_W, CARD_H };

function stack(ids: string[], byId: Map<string, OntologyEntity>, column: LaidOutNode["column"], x: number): LaidOutNode[] {
  return ids.map((id, i) => {
    const e = byId.get(id)!;
    return {
      ...e,
      column,
      x,
      y: PAD_Y + i * (CARD_H + ROW_GAP),
    };
  });
}

/**
 * Simple 3-column DAG: upstream | focus | downstream.
 * Upstream = edges into focus; downstream = edges out of focus.
 * hierarchy mode stacks top→bottom (focus top, children below).
 */
export function layoutNeighborhood(opts: {
  focusId: string;
  entities: OntologyEntity[];
  edges: OntologyEdge[];
  viewMode: ViewMode;
  canvasWidth: number;
  hopDepth: number;
}): { nodes: LaidOutNode[]; edges: LaidOutEdge[]; width: number; height: number } {
  const { focusId, entities, edges, viewMode } = opts;
  const byId = new Map(entities.map((e) => [e.id, e]));
  if (!byId.has(focusId)) {
    return { nodes: [], edges: [], width: 800, height: 400 };
  }

  const upstreamIds = new Set<string>();
  const downstreamIds = new Set<string>();
  for (const e of edges) {
    if (e.targetId === focusId && e.sourceId !== focusId) upstreamIds.add(e.sourceId);
    if (e.sourceId === focusId && e.targetId !== focusId) downstreamIds.add(e.targetId);
  }

  // Soft second-hop: nodes connected to 1-hop but not focus (only if hopDepth>=2)
  if (opts.hopDepth >= 2) {
    const ring = new Set([...upstreamIds, ...downstreamIds]);
    for (const e of edges) {
      if (ring.has(e.sourceId) && e.targetId !== focusId && !upstreamIds.has(e.targetId)) {
        if (upstreamIds.has(e.sourceId)) upstreamIds.add(e.targetId);
        else downstreamIds.add(e.targetId);
      }
      if (ring.has(e.targetId) && e.sourceId !== focusId && !downstreamIds.has(e.sourceId)) {
        if (downstreamIds.has(e.targetId)) downstreamIds.add(e.sourceId);
        else upstreamIds.add(e.sourceId);
      }
    }
  }

  // Avoid putting same node in both columns
  for (const id of [...downstreamIds]) {
    if (upstreamIds.has(id)) downstreamIds.delete(id);
  }

  const up = [...upstreamIds].filter((id) => byId.has(id));
  const down = [...downstreamIds].filter((id) => byId.has(id));

  let nodes: LaidOutNode[] = [];

  if (viewMode === "hierarchy") {
    const x = Math.max(PAD_X, (opts.canvasWidth - CARD_W) / 2);
    const focus: LaidOutNode = {
      ...byId.get(focusId)!,
      column: "focus",
      x,
      y: PAD_Y,
    };
    const children = down.length ? down : up;
    nodes = [
      focus,
      ...children.map((id, i) => ({
        ...byId.get(id)!,
        column: "downstream" as const,
        x: x + ((i % 3) - 1) * (CARD_W + 24),
        y: PAD_Y + CARD_H + ROW_GAP + Math.floor(i / 3) * (CARD_H + ROW_GAP),
      })),
    ];
  } else {
    // relation / chain / path — L→R
    const colW = CARD_W + COL_GAP;
    const midX = Math.max(PAD_X + colW, (opts.canvasWidth - CARD_W) / 2);
    const leftX = midX - colW;
    const rightX = midX + colW;
    nodes = [
      ...stack(up, byId, "upstream", leftX),
      {
        ...byId.get(focusId)!,
        column: "focus",
        x: midX,
        y: PAD_Y + Math.max(0, (Math.max(up.length, down.length) - 1) * (CARD_H + ROW_GAP)) / 2,
      },
      ...stack(down, byId, "downstream", rightX),
    ];
  }

  const nodePos = new Map(nodes.map((n) => [n.id, n]));
  const laidEdges: LaidOutEdge[] = [];
  for (const e of edges) {
    const a = nodePos.get(e.sourceId);
    const b = nodePos.get(e.targetId);
    if (!a || !b) continue;
    laidEdges.push({
      ...e,
      x1: a.x + CARD_W,
      y1: a.y + CARD_H / 2,
      x2: b.x,
      y2: b.y + CARD_H / 2,
    });
  }

  const maxY = nodes.reduce((m, n) => Math.max(m, n.y + CARD_H), 0);
  const maxX = nodes.reduce((m, n) => Math.max(m, n.x + CARD_W), 0);
  return {
    nodes,
    edges: laidEdges,
    width: Math.max(opts.canvasWidth, maxX + PAD_X),
    height: Math.max(400, maxY + PAD_Y),
  };
}

/** BFS shortest path on directed edges (either direction for undirected path view). */
export function findPath(
  edges: OntologyEdge[],
  startId: string,
  endId: string,
): { nodeIds: Set<string>; edgeIds: Set<string> } | null {
  if (startId === endId) return { nodeIds: new Set([startId]), edgeIds: new Set() };
  const adj = new Map<string, { to: string; edgeId: string }[]>();
  for (const e of edges) {
    if (!adj.has(e.sourceId)) adj.set(e.sourceId, []);
    if (!adj.has(e.targetId)) adj.set(e.targetId, []);
    adj.get(e.sourceId)!.push({ to: e.targetId, edgeId: e.id });
    adj.get(e.targetId)!.push({ to: e.sourceId, edgeId: e.id });
  }
  const prev = new Map<string, { from: string; edgeId: string }>();
  const q = [startId];
  const seen = new Set([startId]);
  while (q.length) {
    const cur = q.shift()!;
    for (const n of adj.get(cur) || []) {
      if (seen.has(n.to)) continue;
      seen.add(n.to);
      prev.set(n.to, { from: cur, edgeId: n.edgeId });
      if (n.to === endId) {
        const nodeIds = new Set<string>([endId]);
        const edgeIds = new Set<string>();
        let walk = endId;
        while (walk !== startId) {
          const p = prev.get(walk)!;
          edgeIds.add(p.edgeId);
          nodeIds.add(p.from);
          walk = p.from;
        }
        return { nodeIds, edgeIds };
      }
      q.push(n.to);
    }
  }
  return null;
}
