import { CogneeInstance } from "@/modules/instances/types";

export type TeleologyNodeType = "goal" | "purpose" | "constraint";
export type TeleologyNodeStatus = "proposed" | "active" | "achieved" | "abandoned";
export type TeleologyRelationship = "serves" | "advances" | "blocks";

export interface TeleologyNode {
  id: string;
  name: string;
  status: string;
  description: string;
  keywords: string[];
  type: string;
}

export interface TeleologyStatus {
  enabled: boolean;
  mode: string;
  file_path: string;
  source: string;
  goals: TeleologyNode[];
  purposes: TeleologyNode[];
  constraints: TeleologyNode[];
  goals_total?: number;
  purposes_total?: number;
  constraints_total?: number;
  truncated?: boolean;
  error?: string;
  uploaded_filename?: string;
  created?: TeleologyNode;
  updated?: TeleologyNode;
}

export interface TeleologyNodeInput {
  type: TeleologyNodeType;
  name: string;
  status?: TeleologyNodeStatus;
  description?: string;
  keywords?: string[];
}

export interface GraphNodeSummary {
  id: string;
  name: string;
  type: string;
  description: string;
  status?: string | null;
  cpd_kind?: string | null;
  source?: string | null;
  parent_id?: string | null;
  parent_name?: string | null;
  child_count?: number;
  confirmed_count?: number;
  owner?: string | null;
  created_at?: number | string | null;
  progress?: number | null;
  primary_purpose_id?: string | null;
  primary_purpose_relation?: "serves" | "advances" | null;
}

export interface GraphAnnotation {
  source_id: string;
  source_name: string;
  source_type: string;
  target_id: string;
  target_name: string;
  target_type: string;
  relationship: TeleologyRelationship | string;
  origin?: string | null;
}

export interface GraphAnnotationsPayload {
  dataset_id: string;
  dataset_name?: string | null;
  goals: GraphNodeSummary[];
  goals_total?: number;
  goals_offset?: number;
  goals_truncated?: boolean;
  nodes: GraphNodeSummary[];
  nodes_truncated: boolean;
  annotations: GraphAnnotation[];
  annotations_total?: number;
  annotations_truncated?: boolean;
  yaml_goals: GraphNodeSummary[];
  yaml_goals_total?: number;
}

export interface GoalRelationsPayload {
  items: GraphAnnotation[];
  counts: { serves: number; advances: number; blocks: number };
  total: number;
  offset: number;
  limit: number;
}

export async function getGoalPath(instance: CogneeInstance, datasetId: string, goalId: string): Promise<GraphNodeSummary[]> {
  const params = new URLSearchParams({ dataset_id: datasetId });
  const resp = await instance.fetch(`/v1/teleology/annotations/goals/${encodeURIComponent(goalId)}/path?${params}`);
  if (!resp.ok) throw new Error(await readError(resp));
  return (await resp.json()).path;
}

export async function getGoalDetail(instance: CogneeInstance, datasetId: string, goalId: string): Promise<GraphNodeSummary> {
  const params = new URLSearchParams({ dataset_id: datasetId });
  const resp = await instance.fetch(`/v1/teleology/annotations/goals/${encodeURIComponent(goalId)}/detail?${params}`);
  if (!resp.ok) throw new Error(await readError(resp));
  return (await resp.json()).goal;
}

export async function getGoalRelations(instance: CogneeInstance, datasetId: string, goalId: string, opts?: { relationship?: "serves" | "advances" | "blocks"; limit?: number; offset?: number }): Promise<GoalRelationsPayload> {
  const params = new URLSearchParams({ dataset_id: datasetId, limit: String(opts?.limit ?? 30), offset: String(opts?.offset ?? 0) });
  if (opts?.relationship) params.set("relationship", opts.relationship);
  const resp = await instance.fetch(`/v1/teleology/annotations/goals/${encodeURIComponent(goalId)}/relations?${params}`);
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function createWorkspaceGoal(instance: CogneeInstance, datasetId: string, input: { parentId: string; name: string; description?: string; owner?: string }): Promise<GraphNodeSummary> {
  const resp = await instance.fetch("/v1/teleology/annotations/goals", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dataset_id: datasetId, parent_id: input.parentId, name: input.name, description: input.description || "", owner: input.owner || null }) });
  if (!resp.ok) throw new Error(await readError(resp));
  return (await resp.json()).goal;
}

export async function updateWorkspaceGoal(instance: CogneeInstance, datasetId: string, goalId: string, input: { name?: string; description?: string; owner?: string | null; progress?: number | null; status?: string; primary_purpose_id?: string | null; primary_purpose_relation?: "serves" | "advances" | null }): Promise<GraphNodeSummary> {
  const params = new URLSearchParams({ dataset_id: datasetId });
  const resp = await instance.fetch(`/v1/teleology/annotations/goals/${encodeURIComponent(goalId)}?${params}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) });
  if (!resp.ok) throw new Error(await readError(resp));
  return (await resp.json()).goal;
}

export async function moveWorkspaceGoal(instance: CogneeInstance, datasetId: string, goalId: string, parentId: string): Promise<void> {
  const params = new URLSearchParams({ dataset_id: datasetId });
  const resp = await instance.fetch(`/v1/teleology/annotations/goals/${encodeURIComponent(goalId)}/move?${params}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ parent_id: parentId }) });
  if (!resp.ok) throw new Error(await readError(resp));
}

export async function deleteWorkspaceGoal(instance: CogneeInstance, datasetId: string, goalId: string): Promise<void> {
  const params = new URLSearchParams({ dataset_id: datasetId });
  const resp = await instance.fetch(`/v1/teleology/annotations/goals/${encodeURIComponent(goalId)}?${params}`, { method: "DELETE" });
  if (!resp.ok) throw new Error(await readError(resp));
}

async function readError(resp: Response): Promise<string> {
  const err = await resp.json().catch(() => ({ error: resp.statusText }));
  if (err.error === "proposal_stale") return err.message || "目标上下文已变化，请重新分析后再确认。";
  if (typeof err.error === "string" && err.error) return err.error;
  if (typeof err.detail === "string" && err.detail) return err.detail;
  if (Array.isArray(err.detail) && err.detail[0]?.msg) return String(err.detail[0].msg);
  return `Request failed: ${resp.status}`;
}

export async function getTeleology(
  instance: CogneeInstance,
  opts?: { q?: string; limit?: number; offset?: number },
): Promise<TeleologyStatus> {
  const params = new URLSearchParams();
  if (opts?.q) params.set("q", opts.q);
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  if (opts?.offset != null) params.set("offset", String(opts.offset));
  const qs = params.toString();
  const resp = await instance.fetch(`/v1/teleology${qs ? `?${qs}` : ""}`);
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function createTeleologyNode(
  instance: CogneeInstance,
  input: TeleologyNodeInput,
): Promise<TeleologyStatus> {
  const resp = await instance.fetch("/v1/teleology/nodes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function updateTeleologyNode(
  instance: CogneeInstance,
  id: string,
  input: Partial<TeleologyNodeInput>,
): Promise<TeleologyStatus> {
  const resp = await instance.fetch(`/v1/teleology/nodes/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function deleteTeleologyNode(
  instance: CogneeInstance,
  id: string,
  type?: TeleologyNodeType,
): Promise<TeleologyStatus> {
  const qs = type ? `?node_type=${encodeURIComponent(type)}` : "";
  const resp = await instance.fetch(`/v1/teleology/nodes/${encodeURIComponent(id)}${qs}`, {
    method: "DELETE",
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function uploadTeleology(
  instance: CogneeInstance,
  file: File,
): Promise<TeleologyStatus> {
  const formData = new FormData();
  formData.append("teleology_file", file);
  const resp = await instance.fetch("/v1/teleology", {
    method: "POST",
    body: formData,
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function loadSampleTeleology(instance: CogneeInstance): Promise<TeleologyStatus> {
  const resp = await instance.fetch("/v1/teleology/sample", { method: "POST" });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function clearTeleology(instance: CogneeInstance): Promise<TeleologyStatus> {
  const resp = await instance.fetch("/v1/teleology", { method: "DELETE" });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function getGraphAnnotations(
  instance: CogneeInstance,
  datasetId: string,
  opts?: {
    q?: string;
    limit?: number;
    goalsLimit?: number;
    goalsOffset?: number;
    goalId?: string;
    parentId?: string;
  },
): Promise<GraphAnnotationsPayload> {
  const params = new URLSearchParams({ dataset_id: datasetId });
  if (opts?.q) params.set("q", opts.q);
  if (opts?.limit) params.set("limit", String(opts.limit));
  if (opts?.goalsLimit != null) params.set("goals_limit", String(opts.goalsLimit));
  if (opts?.goalsOffset != null) params.set("goals_offset", String(opts.goalsOffset));
  if (opts?.goalId) params.set("goal_id", opts.goalId);
  if (opts?.parentId) params.set("parent_id", opts.parentId);
  const resp = await instance.fetch(`/v1/teleology/annotations?${params}`);
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function syncTeleologyGoals(
  instance: CogneeInstance,
  datasetId: string,
): Promise<{ dataset_id: string; synced: number; goals: GraphNodeSummary[]; annotations: GraphAnnotation[] }> {
  const params = new URLSearchParams({ dataset_id: datasetId });
  const resp = await instance.fetch(`/v1/teleology/annotations/sync-goals?${params}`, {
    method: "POST",
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function syncTeleologyFromCompanyTree(
  instance: CogneeInstance,
  datasetId: string,
  opts?: { linkEntities?: boolean; sourceRoom?: string },
): Promise<{
  dataset_id: string;
  tree_goals: number;
  advances_created: number;
  serves_created: number;
  yaml_upserted: number;
  goals: GraphNodeSummary[];
  annotations: GraphAnnotation[];
  message?: string;
}> {
  const params = new URLSearchParams({ dataset_id: datasetId });
  params.set("link_entities", opts?.linkEntities ? "true" : "false");
  if (opts?.sourceRoom) params.set("source_room", opts.sourceRoom);
  const resp = await instance.fetch(`/v1/teleology/annotations/sync-from-company-tree?${params}`, {
    method: "POST",
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function createGraphAnnotation(
  instance: CogneeInstance,
  input: {
    datasetId: string;
    sourceId: string;
    targetId: string;
    relationship: TeleologyRelationship;
  },
): Promise<{ created: boolean; annotation: { source_id: string; target_id: string; relationship: string } }> {
  const resp = await instance.fetch("/v1/teleology/annotations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      dataset_id: input.datasetId,
      source_id: input.sourceId,
      target_id: input.targetId,
      relationship: input.relationship,
    }),
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function deleteGraphAnnotation(
  instance: CogneeInstance,
  input: {
    datasetId: string;
    sourceId: string;
    targetId: string;
    relationship: TeleologyRelationship | string;
  },
): Promise<{ deleted: boolean }> {
  const params = new URLSearchParams({
    dataset_id: input.datasetId,
    source_id: input.sourceId,
    target_id: input.targetId,
    relationship: String(input.relationship),
  });
  const resp = await instance.fetch(`/v1/teleology/annotations?${params}`, {
    method: "DELETE",
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export interface PurposeContext {
  dataset_id: string;
  goal: GraphNodeSummary;
  ancestors: GraphNodeSummary[];
  children: GraphNodeSummary[];
  children_total: number;
  children_returned?: number;
  children_truncated?: boolean;
  note: string;
  purposes: GraphNodeSummary[];
  constraints: GraphNodeSummary[];
  relations: GraphAnnotation[];
  entities: GraphNodeSummary[];
  documents: { id: string; name: string; summary: string }[];
  entities_total?: number;
  documents_total?: number;
  entities_truncated?: boolean;
  documents_truncated?: boolean;
  child_evidence?: { goal_id: string; goal_name: string; entities: GraphNodeSummary[]; documents: { id: string; name: string }[] }[];
  source: string | null;
  revision: string | null;
  missing_purpose: boolean;
}

export interface ProposalItem {
  id: string;
  kind: "purpose" | "goal" | "constraint" | "relation" | "gap";
  name: string;
  description: string;
  confidence: number | null;
  reason: string;
  evidence_node_ids?: string[];
  evidence?: { id: string; name: string; type?: string; scope?: string }[];
  weak_reason?: string;
  source_goal_ids: string[];
  relationship?: "serves" | "advances" | "blocks" | null;
  source?: string | null;
  target?: string | null;
  status: "proposed" | "accepted" | "ignored";
}

export interface TeleologyProposal {
  id: string;
  dataset_id: string;
  source_goal_id: string;
  status: "open" | "committed";
  run_id: string;
  created_at: number;
  generated_by: string;
  analysis_summary?: string;
  summary: {
    purposes: number;
    goals: number;
    constraints: number;
    serves: number;
    advances: number;
    blocks: number;
    missing_purpose: number;
  };
  items: ProposalItem[];
  weak_signals?: ProposalItem[];
  open_conflicts?: { type: string; proposal_id?: string; item_id?: string; name?: string }[];
  validation_warnings?: string[];
  context_hash?: string;
}

export interface TeleologyProposalSummary {
  id: string;
  source_goal_id: string;
  status: string;
  generated_by: string;
  run_id: string | null;
  created_at: string;
  analysis_summary?: string;
  items_count: number;
}

export async function listTeleologyProposals(
  instance: CogneeInstance,
  datasetId: string,
  filters: { sourceGoalId?: string; status?: string; generatedBy?: string; limit?: number; offset?: number } = {},
): Promise<{ items: TeleologyProposalSummary[]; total: number }> {
  const params = new URLSearchParams({ dataset_id: datasetId, limit: String(filters.limit ?? 50), offset: String(filters.offset ?? 0) });
  if (filters.sourceGoalId) params.set("source_goal_id", filters.sourceGoalId);
  if (filters.status) params.set("status", filters.status);
  if (filters.generatedBy) params.set("generated_by", filters.generatedBy);
  const resp = await instance.fetch(`/v1/teleology/proposals?${params}`);
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function getTeleologyProposal(instance: CogneeInstance, datasetId: string, proposalId: string): Promise<TeleologyProposal> {
  const params = new URLSearchParams({ dataset_id: datasetId });
  const resp = await instance.fetch(`/v1/teleology/proposals/${encodeURIComponent(proposalId)}?${params}`);
  if (!resp.ok) throw new Error(await readError(resp));
  const raw = await resp.json();
  const items: ProposalItem[] = (raw.items || []).map((item: ProposalItem & { review_status?: ProposalItem["status"] }) => ({ ...item, status: item.review_status || item.status || "proposed" }));
  const count = (kind: ProposalItem["kind"]) => items.filter((item) => item.kind === kind && item.status !== "ignored").length;
  const relationCount = (relationship: string) => items.filter((item) => item.kind === "relation" && item.relationship === relationship && item.status !== "ignored").length;
  return {
    ...raw,
    items,
    summary: raw.summary || { purposes: count("purpose"), goals: count("goal"), constraints: count("constraint"), serves: relationCount("serves"), advances: relationCount("advances"), blocks: relationCount("blocks"), missing_purpose: count("gap") },
  };
}

export async function getLatestOpenGoalProposal(instance: CogneeInstance, datasetId: string, goalId: string): Promise<TeleologyProposal | null> {
  const preferred = await listTeleologyProposals(instance, datasetId, { sourceGoalId: goalId, status: "open", generatedBy: "purpose-agent", limit: 1 });
  const latest = preferred.items[0] || (await listTeleologyProposals(instance, datasetId, { sourceGoalId: goalId, status: "open", limit: 1 })).items[0];
  return latest ? getTeleologyProposal(instance, datasetId, latest.id) : null;
}

export async function getPurposeContext(instance: CogneeInstance, datasetId: string, goalId: string): Promise<PurposeContext> {
  const params = new URLSearchParams({ dataset_id: datasetId });
  const resp = await instance.fetch(`/v1/teleology/annotations/goals/${encodeURIComponent(goalId)}/purpose-context?${params}`);
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function analyzePurpose(instance: CogneeInstance, datasetId: string, goalId: string): Promise<TeleologyProposal> {
  const resp = await instance.fetch("/v1/teleology/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_id: datasetId, goal_id: goalId }),
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function startPurposeReview(instance: CogneeInstance, datasetId: string, goalId: string): Promise<TeleologyProposal> {
  const params = new URLSearchParams({ dataset_id: datasetId });
  const resp = await instance.fetch(`/v1/teleology/annotations/goals/${encodeURIComponent(goalId)}/purpose-review?${params}`, { method: "POST" });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function commitPurposeProposal(
  instance: CogneeInstance,
  datasetId: string,
  proposalId: string,
  acceptedItemIds: string[],
  edits?: Record<string, { name?: string; description?: string; reason?: string }>,
): Promise<{ committed_nodes: { id: string; name: string }[]; skipped_item_ids: string[] }> {
  const resp = await instance.fetch(`/v1/teleology/annotations/purpose-proposals/${encodeURIComponent(proposalId)}/commit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_id: datasetId, accepted_item_ids: acceptedItemIds, edits: edits || null }),
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export interface CoverageRun {
  id: string;
  dataset_id: string;
  mode: "baseline" | "incremental" | "force" | string;
  status: string;
  batch_size: number;
  concurrency: number;
  max_goals?: number | null;
  token_budget?: number | null;
  token_usage_available?: boolean;
  token_budget_active?: boolean;
  used_input_tokens?: number | null;
  used_output_tokens?: number | null;
  total_goals: number;
  scanned_goals?: number;
  eligible_goals: number;
  queued_goals: number;
  processed_goals: number;
  skipped_goals: number;
  proposal_goals: number;
  no_change_goals: number;
  no_context_goals: number;
  failed_goals: number;
}

export interface CoverageStatePage {
  items: { goal_id: string; status: string; dirty_reason?: string | null; retry_count?: number }[];
  total: number;
  summary: Record<string, number>;
}

export async function startCoverageRun(
  instance: CogneeInstance,
  input: {
    dataset_id: string;
    mode: "baseline" | "incremental" | "force";
    batch_size?: number;
    concurrency?: number;
    max_goals?: number | null;
    token_budget?: number | null;
  },
): Promise<CoverageRun> {
  const resp = await instance.fetch("/v1/teleology/coverage/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function getCoverageRun(instance: CogneeInstance, runId: string): Promise<CoverageRun> {
  const resp = await instance.fetch(`/v1/teleology/coverage/runs/${encodeURIComponent(runId)}`);
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export interface CoverageRunCommitResult {
  run_id: string;
  dry_run: boolean;
  proposals_total: number;
  proposals_committable: number;
  empty_proposals: number;
  conflict_proposals: number;
  stale_proposals: string[];
  items_total: number;
  purpose_count: number;
  constraint_count: number;
  goal_count: number;
  serves_count: number;
  advances_count: number;
  blocks_count: number;
  proposal_details: { proposal_id: string; source_goal_id: string; accepted_item_ids: string[]; would_commit_count: number; status: string }[];
  committed_proposals: string[];
  failed_proposals: { proposal_id: string; source_goal_id: string; error_code: string; error_message: string }[];
  skipped_empty: string[];
  already_committed: string[];
  committed_nodes: number;
  committed_relations: number;
  skipped_items: number;
}

export async function commitCoverageRun(instance: CogneeInstance, datasetId: string, runId: string, dryRun: boolean): Promise<CoverageRunCommitResult> {
  const resp = await instance.fetch(`/v1/teleology/coverage/runs/${encodeURIComponent(runId)}/commit-all`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_id: datasetId, dry_run: dryRun }),
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function coverageAction(
  instance: CogneeInstance,
  runId: string,
  action: "pause" | "resume" | "cancel" | "retry-failures",
): Promise<CoverageRun> {
  const resp = await instance.fetch(`/v1/teleology/coverage/runs/${encodeURIComponent(runId)}/${action}`, {
    method: "POST",
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function getCoverageState(instance: CogneeInstance, datasetId: string): Promise<CoverageStatePage> {
  const params = new URLSearchParams({ dataset_id: datasetId, limit: "1" });
  const resp = await instance.fetch(`/v1/teleology/coverage/state?${params}`);
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export interface GoalEvidence {
  node_id: string;
  name: string;
  source_class: string;
  semantic_class?: string;
  layer?: string;
  text?: string;
}

export interface GoalCandidate {
  id: string;
  dataset_id: string;
  name: string;
  description: string;
  confidence: number;
  reason: string;
  source_node_ids: string[];
  evidence: GoalEvidence[];
  parent_candidate_id: string | null;
  status: "proposed" | "confirmed" | "rejected";
  run_id: string;
  generated_by: string;
  semantic_hash: string;
}

export interface GoalTeleologyItem {
  id: string;
  kind: string;
  name: string;
  status: string;
  reason: string;
  confidence: number;
  evidence: GoalEvidence[];
  source_node_ids: string[];
  goal_id?: string;
  relationship?: string | null;
  source?: string | null;
  target?: string | null;
}

export interface GoalModelView {
  dataset_id: string;
  run_id: string | null;
  status: string;
  stage?: string;
  committed: boolean;
  graph_committed: boolean;
  candidates: GoalCandidate[];
  hierarchy: {
    id: string;
    name: string;
    parent_candidate_id: string | null;
    status: string;
    confidence: number;
    evidence_count: number;
  }[];
  purposes: GoalTeleologyItem[];
  constraints: GoalTeleologyItem[];
  relations: GoalTeleologyItem[];
  source_layer_counts?: Record<string, number>;
  semantic_class_counts?: Record<string, number>;
  raw_candidate_count?: number;
  canonical_goal_count?: number;
  rejected_count?: number;
  rejected_by_reason?: Record<string, number>;
  classifications: {
    id: string;
    name: string;
    source_class?: string;
    semantic_class?: string;
    source_layer?: string;
    layer?: string;
    classification_reason?: string;
  }[];
}

export async function getGoalModel(instance: CogneeInstance, datasetId: string): Promise<GoalModelView> {
  const params = new URLSearchParams({ dataset_id: datasetId });
  const resp = await instance.fetch(`/v1/teleology/goal-model?${params}`);
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function startTeleologyBuild(
  instance: CogneeInstance,
  input: {
    dataset_id: string;
    mode: "baseline" | "incremental";
    batch_size?: number;
    concurrency?: number;
    max_sources?: number | null;
  },
): Promise<GoalModelView> {
  const resp = await instance.fetch("/v1/teleology/builds", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}

export async function reviewGoalCandidate(
  instance: CogneeInstance,
  datasetId: string,
  candidateId: string,
  status: "proposed" | "confirmed" | "rejected",
): Promise<{ graph_committed: boolean; committed: boolean }> {
  const resp = await instance.fetch(`/v1/teleology/goal-model/candidates/${encodeURIComponent(candidateId)}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_id: datasetId, status }),
  });
  if (!resp.ok) throw new Error(await readError(resp));
  return resp.json();
}
