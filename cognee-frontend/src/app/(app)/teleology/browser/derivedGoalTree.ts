import type { GoalCandidate, GoalEvidence, GoalModelView, GraphNodeSummary } from "@/modules/teleology/teleologyApi";
import type { GoalPage } from "./NavPanel";
import type { OntologyEdge } from "./types";

const CLASS_LABEL: Record<string, { en: string; zh: string }> = {
  Project: { en: "Project", zh: "项目" },
  Metric: { en: "Metric", zh: "指标" },
  Responsibility: { en: "Responsibility", zh: "责任" },
  Process: { en: "Process", zh: "过程" },
  Document: { en: "Document", zh: "文档" },
  Entity: { en: "Entity", zh: "实体" },
  GoalSignal: { en: "Signal", zh: "信号" },
  Constraint: { en: "Constraint", zh: "约束" },
  Reference: { en: "Reference", zh: "引用" },
  Other: { en: "Data", zh: "数据" },
};

export type DerivedFocus = {
  goal: GraphNodeSummary;
  children: GraphNodeSummary[];
  relations: OntologyEdge[];
  purposes: GraphNodeSummary[];
  constraints: GraphNodeSummary[];
};

export type DerivedGoalTree = {
  roots: GraphNodeSummary[];
  pages: Record<string, GoalPage>;
  statuses: Record<string, string>;
  byId: Map<string, GraphNodeSummary>;
  path: (goalId: string) => GraphNodeSummary[];
  pathIds: (goalId: string) => string[];
  search: (query: string) => GraphNodeSummary[];
  focus: (goalId: string) => DerivedFocus | null;
  /** Evidence and source node ids that belong to a candidate. Not graph goal ids. */
  sourceOwners: Map<string, string>;
};

type EvidenceRow = GoalEvidence & { semantic_class?: string; id?: string };

export function goalVisualId(candidateId: string) {
  return `visual:${candidateId}`;
}

export function dataNodeId(goalId: string, nodeId: string) {
  return `data:${goalId}:${nodeId}`;
}

export function parseDataNodeId(id: string): { goalId: string; nodeId: string } | null {
  if (!id.startsWith("data:")) return null;
  const rest = id.slice("data:".length);
  const split = rest.indexOf(":");
  if (split <= 0) return null;
  return { goalId: rest.slice(0, split), nodeId: rest.slice(split + 1) };
}

export function buildDerivedGoalTree(model: GoalModelView, language: "zh" | "en"): DerivedGoalTree {
  const zh = language === "zh";
  const goals = (model.candidates || []).filter((goal) => goal.status !== "rejected");
  const byGoal = new Map(goals.map((goal) => [goal.id, goal]));
  const hierarchyParent = new Map((model.hierarchy || []).map((row) => [row.id, row.parent_candidate_id || null]));
  const parentOf = (goal: GoalCandidate) => hierarchyParent.has(goal.id) ? hierarchyParent.get(goal.id) || null : goal.parent_candidate_id || null;
  const byId = new Map<string, GraphNodeSummary>();
  const pages: Record<string, GoalPage> = {};
  const statuses: Record<string, string> = {};

  const summary = (goal: GoalCandidate): GraphNodeSummary => {
    const candidateId = goal.id;
    const graphId = goal.graph_id?.trim() || null;
    return {
      id: candidateId,
      candidate_id: candidateId,
      graph_id: graphId,
      visual_id: goalVisualId(candidateId),
      name: goal.name,
      type: "Goal",
      description: goal.description || goal.reason || "",
      source: "derived_goal",
      status: goal.status,
      parent_id: parentOf(goal),
      parent_name: parentOf(goal) ? byGoal.get(parentOf(goal) || "")?.name || null : null,
      child_count: 0,
    };
  };

  const evidenceNode = (goal: GoalCandidate, entry: EvidenceRow): GraphNodeSummary | null => {
    const nodeId = entry.node_id || entry.id || "";
    if (!nodeId) return null;
    const semantic = entry.semantic_class || entry.source_class || "Other";
    const label = CLASS_LABEL[semantic] || CLASS_LABEL.Other;
    const node: GraphNodeSummary = {
      id: dataNodeId(goal.id, nodeId),
      candidate_id: goal.id,
      graph_id: null,
      visual_id: dataNodeId(goal.id, nodeId),
      name: entry.name || nodeId,
      type: "Data",
      description: entry.text || "",
      source: "company_tree",
      parent_id: goal.id,
      parent_name: goal.name,
      child_count: 0,
    };
    statuses[node.id] = zh ? `数据 · ${label.zh}` : `Data · ${label.en}`;
    return node;
  };

  const evidenceByGoal = new Map<string, GraphNodeSummary[]>();
  for (const goal of goals) {
    const node = summary(goal);
    const evidence = (goal.evidence || [])
      .map((entry) => evidenceNode(goal, entry))
      .filter((entry): entry is GraphNodeSummary => Boolean(entry));
    const childGoals = goals.filter((item) => parentOf(item) === goal.id);
    node.child_count = childGoals.length;
    byId.set(node.id, node);
    for (const entry of evidence) byId.set(entry.id, entry);
    evidenceByGoal.set(goal.id, evidence);
    statuses[goal.id] = goal.status === "confirmed"
      ? (zh ? "已确认" : "Confirmed")
      : (zh ? "待确认" : "Proposed");
  }
  for (const goal of goals) {
    const children = goals
      .filter((item) => parentOf(item) === goal.id)
      .map((item) => byId.get(item.id)!)
      .filter(Boolean);
    const evidence = evidenceByGoal.get(goal.id) || [];
    pages[goal.id] = {
      items: [...children, ...evidence],
      total: children.length + evidence.length,
      loading: false,
      loaded: true,
      nextOffset: children.length + evidence.length,
    };
  }

  const sourceOwners = new Map<string, string>();
  for (const goal of goals) {
    for (const sourceId of goal.source_node_ids || []) {
      if (sourceId && !sourceOwners.has(sourceId)) sourceOwners.set(sourceId, goal.id);
    }
    for (const entry of goal.evidence || []) {
      const nodeId = entry.node_id || "";
      if (nodeId && !sourceOwners.has(nodeId)) sourceOwners.set(nodeId, goal.id);
    }
  }

  const roots = goals
    .filter((goal) => !parentOf(goal) || !byGoal.has(parentOf(goal) || ""))
    .map((goal) => byId.get(goal.id)!)
    .filter(Boolean);

  const path = (goalId: string) => {
    const chain: GraphNodeSummary[] = [];
    let current = byId.get(goalId);
    const seen = new Set<string>();
    while (current && current.source === "derived_goal" && !seen.has(current.id)) {
      seen.add(current.id);
      chain.unshift(current);
      current = current.parent_id ? byId.get(current.parent_id) : undefined;
    }
    return chain;
  };

  return {
    roots,
    pages,
    statuses,
    byId,
    path,
    pathIds: (goalId) => path(goalId).map((goal) => goal.id),
    sourceOwners,
    search: (query) => {
      const needle = query.trim().toLowerCase();
      if (!needle) return roots;
      return goals
        .filter((goal) => goal.name.toLowerCase().includes(needle))
        .map((goal) => byId.get(goal.id)!)
        .filter(Boolean);
    },
    focus: (goalId) => {
      const goal = byGoal.get(goalId);
      const node = byId.get(goalId);
      if (!goal || !node || node.source !== "derived_goal") return null;
      const children = (pages[goalId]?.items || []).filter((item) => item.source === "derived_goal");
      const evidence = (pages[goalId]?.items || []).filter((item) => item.source === "company_tree");
      const nameOf = (id: string | null | undefined) => (id && (byGoal.get(id)?.name || byId.get(id)?.name)) || id || "";
      const evidenceRelations: OntologyEdge[] = evidence.map((child) => ({
        id: `${child.id}|evidence|${goal.id}`,
        sourceId: child.id,
        targetId: goal.id,
        sourceName: child.name,
        targetName: goal.name,
        sourceType: "Data",
        targetType: "Goal",
        relationship: "evidence",
      }));
      const semanticRelations: OntologyEdge[] = (model.relations || [])
        .filter((item) => item.status !== "rejected" && (item.goal_id === goalId || item.source === goalId || item.target === goalId))
        .filter((item) => item.source && item.target)
        .map((item) => ({
          id: item.id,
          sourceId: item.source || goalId,
          targetId: item.target || goalId,
          sourceName: nameOf(item.source),
          targetName: nameOf(item.target),
          sourceType: "Goal",
          targetType: "Goal",
          relationship: item.relationship || "serves",
          status: item.status === "confirmed" ? "confirmed" as const : "proposed" as const,
        }));
      const purposes = (model.purposes || [])
        .filter((item) => item.goal_id === goalId && item.status !== "rejected")
        .map((item) => ({ id: item.id, name: item.name, type: "Purpose", description: item.reason || "" }));
      const constraints = (model.constraints || [])
        .filter((item) => item.goal_id === goalId && item.status !== "rejected")
        .map((item) => ({ id: item.id, name: item.name, type: "Constraint", description: item.reason || "" }));
      return { goal: node, children, relations: [...evidenceRelations, ...semanticRelations], purposes, constraints };
    },
  };
}

export type FocusTarget = {
  candidateId: string | null;
  graphId: string | null;
  visualId: string | null;
};

export function resolveFocusTarget(tree: DerivedGoalTree | null, id: string | null | undefined): FocusTarget {
  const empty: FocusTarget = { candidateId: null, graphId: null, visualId: null };
  if (!tree || !id) return empty;
  const data = parseDataNodeId(id);
  if (data) {
    const owner = tree.byId.get(data.goalId);
    if (owner?.source === "derived_goal") {
      const candidateId = owner.candidate_id || data.goalId;
      return { candidateId, graphId: owner.graph_id || null, visualId: owner.visual_id || goalVisualId(candidateId) };
    }
  }
  const bare = id.startsWith("visual:") ? id.slice("visual:".length) : id;
  const direct = tree.byId.get(id) || tree.byId.get(bare);
  if (direct?.source === "derived_goal") {
    const candidateId = direct.candidate_id || direct.id;
    return { candidateId, graphId: direct.graph_id || null, visualId: direct.visual_id || goalVisualId(candidateId) };
  }
  for (const node of tree.byId.values()) {
    if (node.source !== "derived_goal") continue;
    if (node.candidate_id === id || node.visual_id === id || (node.graph_id && node.graph_id === id)) {
      return { candidateId: node.candidate_id || node.id, graphId: node.graph_id || null, visualId: node.visual_id || null };
    }
  }
  for (const node of tree.byId.values()) {
    if (node.source !== "company_tree") continue;
    const parsed = parseDataNodeId(node.visual_id || node.id);
    if (parsed?.nodeId !== id) continue;
    const owner = tree.byId.get(parsed.goalId);
    if (owner?.source !== "derived_goal") continue;
    const candidateId = owner.candidate_id || parsed.goalId;
    return { candidateId, graphId: owner.graph_id || null, visualId: owner.visual_id || goalVisualId(candidateId) };
  }
  const ownerId = tree.sourceOwners.get(id);
  const owner = ownerId ? tree.byId.get(ownerId) : undefined;
  if (owner?.source === "derived_goal") {
    const candidateId = owner.candidate_id || ownerId || owner.id;
    return { candidateId, graphId: owner.graph_id || null, visualId: owner.visual_id || goalVisualId(candidateId) };
  }
  return empty;
}

export function isMissingGraphGoal(message: string) {
  return /goal not found in dataset graph/i.test(message.replace(/['"]/g, ""));
}
