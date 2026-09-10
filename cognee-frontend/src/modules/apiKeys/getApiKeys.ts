import { getLocalApiUrl } from "@/modules/users/getLocalApiUrl";

export interface ApiKey {
  id: string;
  key: string;
  label: string;
  name: string;
}

type ApiErrorBody = {
  detail?: string | { message?: string };
  error?: string | { message?: string };
  message?: string;
};

function messageForStatus(status: number, fallback?: string): string {
  if (fallback) return fallback;
  switch (status) {
    case 400:
      return "Invalid request while loading API keys.";
    case 401:
      return "Your session has expired. Please sign in again.";
    case 403:
      return "You don't have permission to view API keys.";
    case 500:
      return "Something went wrong on the server. Please try again.";
    default:
      return `Failed to load API keys (${status}).`;
  }
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : body.detail?.message;
    const nestedError =
      typeof body.error === "string"
        ? body.error
        : body.error?.message;
    const parsed = detail || nestedError || body.message;
    if (typeof parsed === "string" && parsed.trim()) {
      return messageForStatus(response.status, parsed.trim());
    }
  } catch {
    // Non-JSON body — fall through to status defaults.
  }
  return messageForStatus(response.status);
}

export default async function getApiKeys(_instance?: unknown): Promise<ApiKey[]> {
  const localApiUrl = getLocalApiUrl();

  let response: Response;
  try {
    response = await global.fetch(`${localApiUrl}/api/v1/auth/api-keys`, {
      method: "GET",
      credentials: "include",
    });
  } catch (err) {
    if (err instanceof TypeError) {
      throw new Error(`Cannot connect to the backend at ${localApiUrl}. Is it running?`);
    }
    throw err instanceof Error ? err : new Error("Failed to load API keys.");
  }

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  const data = (await response.json()) as Array<{
    id?: string;
    key?: string;
    label?: string;
    name?: string;
  }>;

  if (!Array.isArray(data)) {
    return [];
  }

  return data.map((item) => ({
    id: String(item.id ?? ""),
    key: item.key ?? "",
    label: item.label ?? "",
    name: item.name ?? item.label ?? "",
  }));
}
