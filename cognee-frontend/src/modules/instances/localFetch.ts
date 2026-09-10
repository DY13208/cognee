import { getLocalApiUrl } from "@/modules/users/getLocalApiUrl";
import { HttpError, toHttpError } from "@/services/http/errors";

let apiKey: string | null = process.env.NEXT_PUBLIC_COGWIT_API_KEY || null;

export default async function localFetch(
  url: URL | RequestInfo,
  options: RequestInit & { timeoutMs?: number } = {},
): Promise<Response> {
  const authHeaders: Record<string, string> = {};
  if (apiKey) {
    authHeaders["X-Api-Key"] = apiKey;
  }

  // The local backend mounts API routes under /api/v1.
  // Most component paths arrive as "/v1/datasets/" etc., but some (like
  // "/configuration/...") omit the version prefix. Default those to /v1.
  let urlStr = typeof url === "string" ? url : url.toString();
  if (!urlStr.startsWith("/")) {
    urlStr = `/${urlStr}`;
  }
  const localApiUrl = getLocalApiUrl();
  const fullUrl = urlStr === "/health" || urlStr.startsWith("/health?")
    ? localApiUrl + urlStr
    : localApiUrl + "/api" + (/^\/v\d+(\/|\?|$)/.test(urlStr) ? urlStr : "/v1" + urlStr);
  const method = options.method || "GET";
  const { timeoutMs, signal: callerSignal, ...fetchInit } = options;

  console.log(`[LOCAL-API] → ${method} ${fullUrl}`);

  // Honour timeoutMs the same way the shared cloud client does — without this,
  // a downed backend leaves uploads/hanging POSTs stuck until the browser gives up.
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  let timeoutController: AbortController | undefined;
  let signal: AbortSignal | undefined = callerSignal ?? undefined;
  if (timeoutMs && timeoutMs > 0) {
    timeoutController = new AbortController();
    timeoutId = setTimeout(
      () => timeoutController!.abort(new DOMException("TimeoutError", "TimeoutError")),
      timeoutMs,
    );
    if (callerSignal) {
      if (callerSignal.aborted) {
        timeoutController.abort(callerSignal.reason);
      } else {
        callerSignal.addEventListener(
          "abort",
          () => timeoutController!.abort(callerSignal.reason),
          { once: true },
        );
      }
    }
    signal = timeoutController.signal;
  }

  try {
    const response = await global.fetch(fullUrl, {
      ...fetchInit,
      signal,
      headers: {
        ...fetchInit.headers,
        ...authHeaders,
      } as HeadersInit,
      credentials: "include",
    });

    console.log(`[LOCAL-API] ← ${method} ${fullUrl} — ${response.status} ${response.statusText}`);

    if (response.status === 401 || response.status === 403) {
      if (typeof window !== "undefined") {
        window.location.href = "/local-login";
      }
      throw new Error("Session expired");
    }

    if (!response.ok) {
      // Preserve status as HttpError so callers (e.g. live-events 409 cursor
      // reset) can branch on it. Plain-object rejects used to wipe the status
      // and also hit console.error → Next.js dev overlay on every poll tick.
      await toHttpError(response);
    }

    return response;
  } catch (error) {
    if (error instanceof HttpError) {
      // warn, not error: expected HTTP failures (409 stale cursor, etc.) must
      // not open the Next.js runtime overlay every 1.5s.
      console.warn(`[LOCAL-API] ✗ ${method} ${fullUrl} — ${error.status} ${error.message}`);
      throw error;
    }

    if (error instanceof Error && error.name === "TimeoutError") {
      console.error(`[LOCAL-API] ✗ ${method} ${fullUrl} — ERROR:`, error);
      throw new Error("Request timed out.");
    }

    if (error instanceof TypeError) {
      console.error(`[LOCAL-API] ✗ ${method} ${fullUrl} — ERROR:`, error);
      throw new Error(`Cannot connect to the backend at ${localApiUrl}. Is it running?`);
    }

    console.error(`[LOCAL-API] ✗ ${method} ${fullUrl} — ERROR:`, error);
    throw error instanceof Error ? error : new Error(String(error));
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
  }
}

export const setApiKey = (newApiKey: string) => {
  apiKey = newApiKey;
};
