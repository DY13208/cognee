import { getLocalApiUrl } from "@/modules/users/getLocalApiUrl";

type ApiErrorBody = {
  detail?: string | { message?: string };
  error?: string | { message?: string };
  message?: string;
};

function messageForStatus(status: number, fallback?: string): string {
  if (fallback) return fallback;
  switch (status) {
    case 400:
      return "Invalid request while deleting the API key.";
    case 401:
      return "Your session has expired. Please sign in again.";
    case 403:
      return "You don't have permission to delete API keys.";
    case 500:
      return "Something went wrong on the server. Please try again.";
    default:
      return `Failed to delete API key (${status}).`;
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

export default async function deleteApiKey(keyId: string): Promise<void> {
  const localApiUrl = getLocalApiUrl();

  let response: Response;
  try {
    response = await global.fetch(`${localApiUrl}/api/v1/auth/api-keys/${encodeURIComponent(keyId)}`, {
      method: "DELETE",
      credentials: "include",
    });
  } catch (err) {
    if (err instanceof TypeError) {
      throw new Error(`Cannot connect to the backend at ${localApiUrl}. Is it running?`);
    }
    throw err instanceof Error ? err : new Error("Failed to delete API key.");
  }

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
}
