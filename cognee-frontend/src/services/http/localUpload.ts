import { HttpError, type ApiErrorBody } from "./errors";
import type { UploadRequestOpts } from "@/modules/instances/types";
import { getLocalApiUrl } from "@/modules/users/getLocalApiUrl";

// Mirrors podUpload's 429 retry budget — local backends can also return
// Retry-After when another pipeline is mid-flight.
const MAX_RETRIES_429 = 3;
const DEFAULT_RETRY_AFTER_MS = 5_000;

function parseBody(text: string): ApiErrorBody | string {
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed && typeof parsed === "object") return parsed as ApiErrorBody;
  } catch {
    /* not JSON — fall through to the raw text */
  }
  return text;
}

function errorMessage(body: ApiErrorBody | string, statusText: string): string {
  if (typeof body === "string") return body || statusText;
  return String(body.detail ?? body.error ?? body.message ?? statusText);
}

function retryAfterMs(header: string | null): number {
  if (!header) return DEFAULT_RETRY_AFTER_MS;
  const seconds = parseFloat(header);
  if (!Number.isNaN(seconds)) return Math.max(0, seconds * 1000);
  const date = Date.parse(header);
  if (!Number.isNaN(date)) return Math.max(0, date - Date.now());
  return DEFAULT_RETRY_AFTER_MS;
}

/** Resolve a CogneeInstance path (e.g. "/v1/add") to the local backend URL. */
export function resolveLocalApiUrl(path: string): string {
  let urlStr = path.startsWith("/") ? path : `/${path}`;
  const localApiUrl = getLocalApiUrl();
  if (urlStr === "/health" || urlStr.startsWith("/health?")) {
    return localApiUrl + urlStr;
  }
  return (
    localApiUrl +
    "/api" +
    (/^\/v\d+(\/|\?|$)/.test(urlStr) ? urlStr : "/v1" + urlStr)
  );
}

/**
 * Multipart POST to the self-hosted backend over XHR — needed so the upload
 * progress bar can move. Cookie session auth (`withCredentials`) replaces the
 * cloud pod's X-Api-Key header.
 */
export default function localUpload(
  path: string,
  body: FormData,
  { timeoutMs, signal, onProgress }: UploadRequestOpts = {},
): Promise<Response> {
  const url = resolveLocalApiUrl(path);

  return new Promise<Response>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }

    const xhr = new XMLHttpRequest();
    xhr.open("POST", url, true);
    xhr.withCredentials = true;
    xhr.responseType = "text";
    if (timeoutMs) xhr.timeout = timeoutMs;

    const onAbort = (): void => xhr.abort();
    signal?.addEventListener("abort", onAbort, { once: true });
    const cleanup = (): void => signal?.removeEventListener("abort", onAbort);

    if (onProgress) {
      xhr.upload.onprogress = (event: ProgressEvent): void => {
        if (event.lengthComputable) onProgress(event.loaded, event.total);
      };
    }

    xhr.onload = (): void => {
      cleanup();
      const text = xhr.responseText ?? "";
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(new Response(text, { status: xhr.status, statusText: xhr.statusText }));
        return;
      }
      const parsed = parseBody(text);
      reject(
        new HttpError(
          xhr.status,
          xhr.statusText,
          errorMessage(parsed, xhr.statusText),
          parsed,
          xhr.getResponseHeader("Retry-After"),
        ),
      );
    };

    xhr.onerror = (): void => {
      cleanup();
      reject(
        new Error(
          `Cannot connect to the backend at ${getLocalApiUrl()}. Is it running?`,
        ),
      );
    };

    xhr.ontimeout = (): void => {
      cleanup();
      reject(new Error("Request timed out."));
    };

    xhr.onabort = (): void => {
      cleanup();
      reject(new DOMException("Aborted", "AbortError"));
    };

    xhr.send(body);
  });
}

export async function localUploadWithRetry(
  path: string,
  makeBody: () => FormData,
  opts: UploadRequestOpts = {},
): Promise<Response> {
  let attempt = 0;
  for (;;) {
    try {
      return await localUpload(path, makeBody(), opts);
    } catch (error) {
      const isThrottled = error instanceof HttpError && error.status === 429;
      if (!isThrottled || attempt >= MAX_RETRIES_429) throw error;
      const fromBody =
        typeof error.body === "object" && error.body !== null && "retry_after_seconds" in error.body
          ? String((error.body as Record<string, unknown>).retry_after_seconds)
          : null;
      await new Promise((r) =>
        setTimeout(r, retryAfterMs(error.retryAfter ?? fromBody)),
      );
      attempt += 1;
    }
  }
}
