import { CogneeInstance } from "@/modules/instances/types";

export type TeleologyNodeType = "goal" | "purpose" | "constraint";
export type TeleologyNodeStatus = "proposed" | "active" | "achieved" | "abandoned";

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

async function readError(resp: Response): Promise<string> {
  const err = await resp.json().catch(() => ({ error: resp.statusText }));
  return err.error || `Request failed: ${resp.status}`;
}

export async function getTeleology(instance: CogneeInstance): Promise<TeleologyStatus> {
  const resp = await instance.fetch("/v1/teleology");
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
