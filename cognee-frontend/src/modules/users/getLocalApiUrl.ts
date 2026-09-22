import { readRuntimeConfig, stripTrailingSlash } from "@/modules/config/runtimeConfig";

// This project publishes the local API on host port 8320 (the container
// continues to listen on 8000 internally). Keep the browser fallback aligned
// with that published port so a missing runtime-config script cannot send the
// UI to an unrelated/closed localhost:8000.
const DEFAULT_LOCAL_API_PORT = "8320";

export function getLocalApiUrl(): string {
  // Runtime config wins for an explicit absolute backend URL: it is the only
  // source a published Docker image can change, because NEXT_PUBLIC_* is frozen
  // into the bundle at build time.
  const runtime = readRuntimeConfig();
  if (runtime.backendUrl) return stripTrailingSlash(runtime.backendUrl);

  const configuredUrl = process.env.NEXT_PUBLIC_LOCAL_API_URL;
  if (configuredUrl) return stripTrailingSlash(configuredUrl);

  // No fixed hostname: reuse whatever host the user opened the UI with
  // (localhost, LAN IP, or a public DNS name) so auth cookies stay same-site.
  // `backendPort` is the host-mapped API port (compose `8320:8000` → 8320).
  // readRuntimeConfig() already falls back to a memory/session cache when the
  // head script is briefly missing (HMR / head reconciliation).
  const port = runtime.backendPort || DEFAULT_LOCAL_API_PORT;

  if (
    typeof window !== "undefined" &&
    !runtime.backendPort &&
    port === DEFAULT_LOCAL_API_PORT
  ) {
    console.warn(
      "[cognee] backendPort missing from runtime config; falling back to " +
        `${DEFAULT_LOCAL_API_PORT}. If the API is published on a different host ` +
        "port, set COGNEE_BACKEND_PORT on the UI container.",
    );
  }

  if (typeof window !== "undefined") {
    // HTTPS UI entry (codebuddy-https on :3030, or public TLS) proxies the API
    // at same-origin `/backend`. Port 8320 is plain HTTP only — deriving
    // `https://{host}:8320` makes the browser fail the TLS handshake and the
    // LocalProvider surfaces "Cannot connect to local Cognee backend".
    if (window.location.protocol === "https:") {
      return stripTrailingSlash(`${window.location.origin}/backend`);
    }
    return `http://${window.location.hostname}:${port}`;
  }

  return `http://localhost:${port}`;
}
