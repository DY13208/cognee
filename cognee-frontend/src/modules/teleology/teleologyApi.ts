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
}

export interface GraphAnnotation {
  source_id: string;
  source_name: string;
  source_type: string;
  target_id: string;
  target_name: string;
  target_type: string;
  relationship: TeleologyRelationship | string;
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

async function readError(resp: Response): Promise<string> {
  const err = await resp.json().catch(() => ({ error: resp.statusText }));
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
  if (opts?.linkEntities === false) params.set("link_entities", "false");
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
