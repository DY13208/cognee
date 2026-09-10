/**
 * Configuration the Next server hands to the browser on every request.
 *
 * `NEXT_PUBLIC_*` values are inlined into the client bundle when the app is
 * built, so a published Docker image cannot be pointed at a different backend
 * with `docker run -e ...`: every reader would still see whatever URL was
 * baked in at build time. The server shell therefore renders the live
 * environment into the document, and client readers prefer it over the
 * build-time constant.
 *
 * It travels as `<script type="application/json">` in <head> rather than as an
 * executable script, which removes the question of ordering. An executing
 * snippet has to win a race against Next's async framework chunks, and
 * next/script's "beforeInteractive" does not even try: it queues the URL for
 * Next's own runtime to fetch after the bundle. Inert JSON needs only to be
 * parsed, and <head> is finished before the body root element exists, so the
 * data is in the DOM before React can render the component that reads it.
 */

export const RUNTIME_CONFIG_ELEMENT_ID = "cognee-runtime-config";

export interface RuntimeConfig {
  /** Absolute origin of the cognee backend, without a trailing slash. */
  backendUrl: string | null;
  /**
   * Host-published API port used when `backendUrl` is unset. The browser then
   * builds `http(s)://{page-hostname}:{backendPort}` so the same UI works via
   * localhost and via LAN IP without baking a hostname into the container.
   */
  backendPort: string | null;
}

/**
 * Callers concatenate paths onto the backend URL ("/api/v1/..."), so a
 * trailing slash would produce "//api" and miss on the backend.
 */
export function stripTrailingSlash(url: string): string {
  return url.replace(/\/+$/, "");
}

/**
 * Normalise a configured backend URL, or return null when nothing is set.
 *
 * Throws when the value is set but unusable. A container started with a broken
 * URL should say so in its logs, rather than quietly falling back to localhost
 * and failing every request for a reason the operator cannot see.
 */
export function normalizeBackendUrl(
  raw: string | undefined | null,
  source: string,
): string | null {
  const value = raw?.trim();
  if (!value) return null;

  // Checked before parsing, because "cognee:8000" (the most likely mistake)
  // is a *valid* URL with the scheme "cognee:", and reporting it as a protocol
  // problem tells the operator nothing about what to type instead.
  if (!/^https?:\/\//i.test(value)) {
    throw new Error(
      `${source} must be an absolute http(s) URL, got "${value}". Expected something like "http://localhost:8000".`,
    );
  }

  try {
    new URL(value);
  } catch {
    throw new Error(`${source} is not a valid URL: "${value}".`);
  }

  return stripTrailingSlash(value);
}

/**
 * Accept a host-mapped backend port (e.g. compose `8320:8000` → `8320`).
 * Returns null when unset/blank; throws when set but not a usable TCP port.
 */
export function normalizeBackendPort(
  raw: string | undefined | null,
  source = "COGNEE_BACKEND_PORT",
): string | null {
  const value = raw?.trim();
  if (!value) return null;
  if (!/^\d{1,5}$/.test(value)) {
    throw new Error(`${source} must be a TCP port number, got "${value}".`);
  }
  const port = Number(value);
  if (port < 1 || port > 65535) {
    throw new Error(`${source} must be between 1 and 65535, got "${value}".`);
  }
  return value;
}

const RUNTIME_CONFIG_STORAGE_KEY = "cognee.runtimeConfig";

/** In-memory copy of the last usable runtime config (survives brief DOM gaps). */
let cachedRuntimeConfig: Partial<RuntimeConfig> | null = null;

/** Test helper — drop module + session caches between cases. */
export function clearRuntimeConfigCache(): void {
  cachedRuntimeConfig = null;
  if (typeof sessionStorage !== "undefined") {
    try {
      sessionStorage.removeItem(RUNTIME_CONFIG_STORAGE_KEY);
    } catch {
      // Private mode / disabled storage.
    }
  }
}

function persistRuntimeConfig(config: Partial<RuntimeConfig>): void {
  if (!config.backendUrl && !config.backendPort) return;
  cachedRuntimeConfig = config;
  if (typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.setItem(RUNTIME_CONFIG_STORAGE_KEY, JSON.stringify(config));
  } catch {
    // Quota / private mode — memory cache still helps within the tab life.
  }
}

function readPersistedRuntimeConfig(): Partial<RuntimeConfig> {
  if (cachedRuntimeConfig) return cachedRuntimeConfig;
  if (typeof sessionStorage === "undefined") return {};
  try {
    const raw = sessionStorage.getItem(RUNTIME_CONFIG_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Partial<RuntimeConfig>;
    cachedRuntimeConfig = parsed;
    return parsed;
  } catch {
    return {};
  }
}

function parseRuntimeConfigPayload(text: string): Partial<RuntimeConfig> {
  let parsed: Partial<RuntimeConfig>;
  try {
    parsed = JSON.parse(text) as Partial<RuntimeConfig>;
  } catch {
    return {};
  }

  const result: Partial<RuntimeConfig> = {};

  // Re-check the URL on the way out of the DOM, with the same rule the server
  // applied on the way in. The client should not trust document content it did
  // not verify itself: this value reaches href attributes, so an unvalidated
  // "javascript:" here would be an XSS sink.
  //
  // The scheme is not carried over from the input, it is picked from the two
  // literals below and the rest is rebuilt from the parsed parts. That leaves
  // no way for the document to choose the scheme, and it is why static
  // analysis can see the result is safe. Query and fragment are dropped; a
  // backend base URL has no use for them. Anything unusable degrades to the
  // caller's own fallback rather than throwing.
  const raw = parsed.backendUrl?.trim();
  if (raw) {
    try {
      const url = new URL(raw);
      if (url.protocol === "https:") {
        result.backendUrl = stripTrailingSlash(`https://${url.host}${url.pathname}`);
      } else if (url.protocol === "http:") {
        result.backendUrl = stripTrailingSlash(`http://${url.host}${url.pathname}`);
      }
    } catch {
      // Unparseable — leave backendUrl unset.
    }
  }

  try {
    const port = normalizeBackendPort(
      typeof parsed.backendPort === "string" || typeof parsed.backendPort === "number"
        ? String(parsed.backendPort)
        : null,
    );
    if (port) result.backendPort = port;
  } catch {
    // Bad port in the document — ignore; caller may use a cached / default port.
  }

  return result;
}

/**
 * Client-side read of the config the server rendered into the document.
 *
 * Never throws: a missing or malformed element just means "not configured",
 * and the caller's own fallback is a better outcome than a blank page.
 *
 * Next/Turbopack HMR and App Router head reconciliation can briefly detach the
 * `<script id="cognee-runtime-config">` tag. Without a cache, that race makes
 * `getLocalApiUrl()` fall back to port 8000 while the API is published on
 * 8320 — the intermittent "Cannot connect … :8000" error on LAN setups.
 */
export function readRuntimeConfig(): Partial<RuntimeConfig> {
  if (typeof document === "undefined") return readPersistedRuntimeConfig();

  const element = document.getElementById(RUNTIME_CONFIG_ELEMENT_ID);
  if (element?.textContent) {
    const fromDom = parseRuntimeConfigPayload(element.textContent);
    if (fromDom.backendUrl || fromDom.backendPort) {
      persistRuntimeConfig(fromDom);
      return fromDom;
    }
  }

  return readPersistedRuntimeConfig();
}

/**
 * Serialise for embedding in the document. Escaped even though the payload is
 * inert JSON: without it a value containing "</script>" would close the tag
 * early and spill the rest into the page as markup.
 */
export function serializeRuntimeConfig(config: RuntimeConfig): string {
  return JSON.stringify(config)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}
