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
};

type EvidenceRow = GoalEvidence & { semantic_class?: string; id?: string };

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
  const byId = new Map<string, GraphNodeSummary>();
  const pages: Record<string, GoalPage> = {};
  const statuses: Record<string, string> = {};

  const summary = (goal: GoalCandidate): GraphNodeSummary => ({
    id: goal.id,
    name: goal.name,
    type: "Goal",
    description: goal.description || goal.reason || "",
    source: "derived_goal",
    status: goal.status,
    parent_id: goal.parent_candidate_id,
    parent_name: goal.parent_candidate_id ? byGoal.get(goal.parent_candidate_id)?.name || null : null,
    child_count: 0,
  });

  const evidenceNode = (goal: GoalCandidate, entry: EvidenceRow): GraphNodeSummary | null => {
    const nodeId = entry.node_id || entry.id || "";
    if (!nodeId) return null;
    const semantic = entry.semantic_class || entry.source_class || "Other";
    const label = CLASS_LABEL[semantic] || CLASS_LABEL.Other;
    const node: GraphNodeSummary = {
      id: dataNodeId(goal.id, nodeId),
      name: entry.name || nodeId,
      type: semantic,
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
    const childGoals = goals.filter((item) => item.parent_candidate_id === goal.id);
    node.child_count = childGoals.length + evidence.length;
    byId.set(node.id, node);
    for (const entry of evidence) byId.set(entry.id, entry);
    evidenceByGoal.set(goal.id, evidence);
    statuses[goal.id] = goal.status === "confirmed"
      ? (zh ? "已确认" : "Confirmed")
      : (zh ? "待确认" : "Proposed");
  }
  for (const goal of goals) {
    const children = goals
      .filter((item) => item.parent_candidate_id === goal.id)
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

  const roots = goals
    .filter((goal) => !goal.parent_candidate_id || !byGoal.has(goal.parent_candidate_id))
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
      const children = pages[goalId]?.items.filter((item) => item.source === "company_tree") || [];
      const relations: OntologyEdge[] = children.map((child) => ({
        id: `${child.id}|serves|${goal.id}`,
        sourceId: child.id,
        targetId: goal.id,
        sourceName: child.name,
        targetName: goal.name,
        sourceType: child.type,
        targetType: "Goal",
        relationship: "serves",
      }));
      const purposes = (model.purposes || [])
        .filter((item) => item.goal_id === goalId && item.status !== "rejected")
        .map((item) => ({ id: item.id, name: item.name, type: "Purpose", description: item.reason || "" }));
      const constraints = (model.constraints || [])
        .filter((item) => item.goal_id === goalId && item.status !== "rejected")
        .map((item) => ({ id: item.id, name: item.name, type: "Constraint", description: item.reason || "" }));
      return { goal: node, children, relations, purposes, constraints };
    },
  };
}
