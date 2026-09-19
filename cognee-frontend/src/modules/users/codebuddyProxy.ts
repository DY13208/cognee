import "server-only";
import { getServerBackendUrl } from "@/modules/config/serverRuntimeConfig";

/** Forward only the OAuth protocol fields; all provider credentials live in Python. */
export async function proxyCodeBuddy(request: Request, action: "login" | "callback") {
  const target = new URL(`${getServerBackendUrl()}/api/v1/auth/codebuddy/${action}`);
  const payload: Record<string, string> = {};
  if (action === "callback") {
    const incoming = new URL(request.url);
    for (const key of ["code", "state", "error"]) {
      const value = incoming.searchParams.get(key);
      if (value) payload[key] = value;
    }
  }
  try {
    const upstream = await fetch(target, {
      method: action === "callback" ? "POST" : "GET",
      body: action === "callback" ? JSON.stringify(payload) : undefined,
      headers: { cookie: request.headers.get("cookie") || "", "Content-Type": "application/json" },
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(45_000),
    });
    const headers = new Headers({ "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" });
    for (const cookie of upstream.headers.getSetCookie()) headers.append("Set-Cookie", cookie);
    const location = upstream.headers.get("location");
    if (location && upstream.status >= 300 && upstream.status < 400) {
      headers.set("Location", location);
      return new Response(null, { status: 303, headers });
    }
    // Only the backend's explicit configuration error means setup is missing.
    const detail = upstream.status === 503
      ? await upstream.json().catch(() => null) : null;
    const errorCode = detail?.detail === "WorkBuddy login is not configured"
      ? "not_configured" : "provider_unavailable";
    console.warn("WorkBuddy OAuth proxy failed", { action, status: upstream.status, errorCode });
    headers.set("Location", `/local-login?error=${errorCode}`);
    return new Response(null, { status: 303, headers });
  } catch {
    return new Response(null, {
      status: 303,
      headers: { Location: "/local-login?error=provider_unavailable", "Cache-Control": "no-store" },
    });
  }
}
