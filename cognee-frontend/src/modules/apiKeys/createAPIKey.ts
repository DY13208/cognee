import { getLocalApiUrl } from "@/modules/users/getLocalApiUrl";

export interface CreatedApiKey {
  id: string;
  key: string;
}

// Mirrors the SaaS module's result shape — the synced ApiKeysPage and
// CreateApiKeyButton read `.ok`/`.error`/`.key` and must not care which build
// they're running in.
export type CreateApiKeyResult =
  | { ok: true; key: CreatedApiKey | null }
  | { ok: false; error: string; status?: number };

type ApiErrorBody = {
  detail?: string | { message?: string };
  error?: string | { message?: string };
  message?: string;
};

function messageForStatus(status: number, fallback?: string): string {
  if (fallback) return fallback;
  switch (status) {
    case 400:
      return "Invalid request. Please check the key name and try again.";
    case 401:
      return "Your session has expired. Please sign in again.";
    case 403:
      return "You don't have permission to create API keys.";
    case 500:
      return "Something went wrong on the server. Please try again.";
    default:
      return `Failed to create API key (${status}).`;
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

export default async function createApiKey(
  options: { name?: string; noRedirectOnAuth?: boolean } = {},
): Promise<CreateApiKeyResult> {
  const { name, noRedirectOnAuth = false } = options;
  const localApiUrl = getLocalApiUrl();

  try {
    const response = await global.fetch(`${localApiUrl}/api/v1/auth/api-keys`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name ?? null }),
      credentials: "include",
    });

    if (response.ok) {
      const data = (await response.json()) as {
        id?: string;
        key?: string;
      };
      if (data?.id && data?.key) {
        return { ok: true, key: { id: String(data.id), key: data.key } };
      }
      // Key was created but the clear-text value was missing — surface null so
      // the page can tell the user to revoke and recreate.
      return { ok: true, key: null };
    }

    if (
      (response.status === 401 || response.status === 403) &&
      !noRedirectOnAuth &&
      typeof window !== "undefined"
    ) {
      window.location.href = "/local-login";
    }

    return {
      ok: false,
      error: await readErrorMessage(response),
      status: response.status,
    };
  } catch (err) {
    if (err instanceof TypeError) {
      return {
        ok: false,
        error: `Cannot connect to the backend at ${localApiUrl}. Is it running?`,
      };
    }
    const message = err instanceof Error ? err.message : "Failed to create API key.";
    return { ok: false, error: message };
  }
}
