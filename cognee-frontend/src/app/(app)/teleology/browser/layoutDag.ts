import type { LaidOutEdge, LaidOutNode, OntologyEdge, OntologyEntity, ViewMode } from "./types";

const CARD_W = 200;
const CARD_H = 80;
const COL_GAP = 120;
const ROW_GAP = 36;
const LEVEL_GAP = 56;
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

/** Parent → children from CPD/teleology edges (has_subgoal parent→child, advances child→parent). */
export function buildTreeChildren(edges: OntologyEdge[]): Map<string, string[]> {
  const children = new Map<string, string[]>();
  const seen = new Set<string>();
  const add = (parent: string, child: string) => {
    if (!parent || !child || parent === child) return;
    const key = `${parent}>${child}`;
    if (seen.has(key)) return;
    seen.add(key);
    if (!children.has(parent)) children.set(parent, []);
    children.get(parent)!.push(child);
  };
  for (const e of edges) {
    const rel = e.relationship.toLowerCase();
    if (rel === "has_subgoal" || rel === "has_detail_reference") {
      add(e.sourceId, e.targetId);
    } else if (rel === "advances") {
      // Teleology remaps tree as child → parent
      add(e.targetId, e.sourceId);
    }
  }
  return children;
}

function layoutCpdTree(opts: {
  focusId: string;
  entities: OntologyEntity[];
  edges: OntologyEdge[];
  canvasWidth: number;
  hopDepth: number;
}): { nodes: LaidOutNode[]; edges: LaidOutEdge[]; width: number; height: number } {
  const byId = new Map(opts.entities.map((e) => [e.id, e]));
  if (!byId.has(opts.focusId)) {
    return { nodes: [], edges: [], width: 800, height: 400 };
  }

  const childrenOf = buildTreeChildren(opts.edges);
  // Only keep children that exist in the current entity set
  for (const [pid, kids] of [...childrenOf.entries()]) {
    childrenOf.set(
      pid,
      kids.filter((id) => byId.has(id)),
    );
  }

  // Walk up to a display root: prefer the highest ancestor within hopDepth,
  // else the focus itself (subtree).
  let rootId = opts.focusId;
  const parentOf = new Map<string, string>();
  for (const [p, kids] of childrenOf) {
    for (const c of kids) parentOf.set(c, p);
  }
  let walk = opts.focusId;
  for (let i = 0; i < Math.max(0, opts.hopDepth - 1); i += 1) {
    const p = parentOf.get(walk);
    if (!p || !byId.has(p)) break;
    walk = p;
    rootId = p;
  }

  // BFS levels from root — hopDepth is how many child levels below the display root.
  const levels: string[][] = [];
  const placed = new Set<string>();
  let frontier = [rootId];
  placed.add(rootId);
  const maxLevels = Math.max(1, opts.hopDepth) + 1;
  while (frontier.length && levels.length < maxLevels) {
    levels.push(frontier);
    const next: string[] = [];
    for (const id of frontier) {
      for (const c of childrenOf.get(id) || []) {
        if (placed.has(c)) continue;
        placed.add(c);
        next.push(c);
      }
    }
    frontier = next;
  }

  // Horizontal spacing: equal slots per level, centered
  const nodes: LaidOutNode[] = [];
  let maxX = 0;
  levels.forEach((level, li) => {
    const span = Math.max(opts.canvasWidth - 2 * PAD_X, level.length * (CARD_W + 24));
    const step = level.length > 1 ? span / (level.length - 1) : 0;
    const startX =
      level.length === 1
        ? Math.max(PAD_X, (opts.canvasWidth - CARD_W) / 2)
        : PAD_X + Math.max(0, (opts.canvasWidth - 2 * PAD_X - span) / 2);
    level.forEach((id, i) => {
      const e = byId.get(id)!;
      const x = level.length === 1 ? startX : startX + i * step;
      const y = PAD_Y + li * (CARD_H + LEVEL_GAP);
      nodes.push({
        ...e,
        column: id === opts.focusId ? "focus" : li === 0 ? "upstream" : "downstream",
        x,
        y,
      });
      maxX = Math.max(maxX, x + CARD_W);
    });
  });

  const nodePos = new Map(nodes.map((n) => [n.id, n]));
  const laidEdges: LaidOutEdge[] = [];
  for (const e of opts.edges) {
    const a = nodePos.get(e.sourceId);
    const b = nodePos.get(e.targetId);
    if (!a || !b) continue;
    const rel = e.relationship.toLowerCase();
    // Tree edges: draw parent → child (top → bottom)
    let parent = a;
    let child = b;
    if (rel === "advances") {
      parent = b;
      child = a;
    } else if (rel !== "has_subgoal" && rel !== "has_detail_reference") {
      // Non-tree edges still drawn between cards (mid sides)
      laidEdges.push({
        ...e,
        x1: a.x + CARD_W / 2,
        y1: a.y + CARD_H,
        x2: b.x + CARD_W / 2,
        y2: b.y,
      });
      continue;
    }
    laidEdges.push({
      ...e,
      x1: parent.x + CARD_W / 2,
      y1: parent.y + CARD_H,
      x2: child.x + CARD_W / 2,
      y2: child.y,
    });
  }

  const maxY = nodes.reduce((m, n) => Math.max(m, n.y + CARD_H), 0);
  return {
    nodes,
    edges: laidEdges,
    width: Math.max(opts.canvasWidth, maxX + PAD_X),
    height: Math.max(400, maxY + PAD_Y),
  };
}

/**
 * Simple 3-column DAG: upstream | focus | downstream.
 * Hierarchy mode lays out the CPD parent→child tree top→bottom.
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

  if (viewMode === "hierarchy") {
    return layoutCpdTree(opts);
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

  for (const id of [...downstreamIds]) {
    if (upstreamIds.has(id)) downstreamIds.delete(id);
  }

  const up = [...upstreamIds].filter((id) => byId.has(id));
  const down = [...downstreamIds].filter((id) => byId.has(id));

  const colW = CARD_W + COL_GAP;
  const midX = Math.max(PAD_X + colW, (opts.canvasWidth - CARD_W) / 2);
  const leftX = midX - colW;
  const rightX = midX + colW;
  const nodes: LaidOutNode[] = [
    ...stack(up, byId, "upstream", leftX),
    {
      ...byId.get(focusId)!,
      column: "focus",
      x: midX,
      y: PAD_Y + Math.max(0, (Math.max(up.length, down.length) - 1) * (CARD_H + ROW_GAP)) / 2,
    },
    ...stack(down, byId, "downstream", rightX),
  ];

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
