// Server-side only. Without this guard, a client component importing this
// module would get process.env.COGNEE_BACKEND_URL replaced with undefined at
// build time and silently fall back to localhost. next/jest maps this to an
// empty mock, so tests are unaffected.
import "server-only";

import {
  normalizeBackendPort,
  normalizeBackendUrl,
  type RuntimeConfig,
} from "./runtimeConfig";

/**
 * Read at request time, which is what lets one published image serve any
 * backend. Deliberately not NEXT_PUBLIC_-prefixed: that prefix means "inline
 * this at build time", the exact behaviour this variable exists to avoid.
 */
const BACKEND_URL_ENV = "COGNEE_BACKEND_URL";
const BACKEND_PORT_ENV = "COGNEE_BACKEND_PORT";

/** Still honoured so builds that baked in a URL keep working. */
const BUILD_TIME_ENV = "NEXT_PUBLIC_LOCAL_API_URL";

const DEFAULT_BACKEND_URL = "http://localhost:8000";

/** The backend this server process should call from route handlers. */
export function getServerBackendUrl(): string {
  return (
    normalizeBackendUrl(process.env.COGNEE_BACKEND_URL, BACKEND_URL_ENV) ??
    normalizeBackendUrl(process.env.NEXT_PUBLIC_LOCAL_API_URL, BUILD_TIME_ENV) ??
    DEFAULT_BACKEND_URL
  );
}

/**
 * The config advertised to the browser.
 *
 * Prefer leaving COGNEE_BACKEND_URL unset and setting COGNEE_BACKEND_PORT to
 * the host-mapped API port. The browser then derives
 * `{page-protocol}//{page-hostname}:{backendPort}`, so the same container
 * works when opened via localhost or via a LAN/public IP. An explicit
 * COGNEE_BACKEND_URL still wins when you need a fixed absolute origin.
 */
export function collectRuntimeConfig(): RuntimeConfig {
  return {
    backendUrl: normalizeBackendUrl(process.env.COGNEE_BACKEND_URL, BACKEND_URL_ENV),
    backendPort: normalizeBackendPort(process.env.COGNEE_BACKEND_PORT, BACKEND_PORT_ENV),
  };
}
