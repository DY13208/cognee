import "server-only";
import { getServerBackendUrl } from "@/modules/config/serverRuntimeConfig";

export async function isMindMapSsoEnabled(): Promise<boolean> {
  try {
    const response = await fetch(`${getServerBackendUrl()}/api/v1/auth/mind-map/config`, {
      cache: "no-store", signal: AbortSignal.timeout(5_000),
    });
    return response.ok && (await response.json()).enabled === true;
  } catch {
    return false;
  }
}

/** Codes are forwarded in the body; provider secrets and PKCE stay on the servers. */
export async function proxyMindMapSso(request: Request, action: "login" | "callback" | "qr") {
  const target = `${getServerBackendUrl()}/api/v1/auth/mind-map/${action}`;
  const payload: Record<string, string> = {};
  if (action === "callback") {
    const incoming = new URL(request.url);
    for (const key of ["code", "state", "error"]) {
      const value = incoming.searchParams.get(key);
      if (value) payload[key] = value;
    }
  }
  const headers = new Headers({ "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" });
  try {
    const upstream = await fetch(target, {
      method: action === "callback" ? "POST" : "GET",
      body: action === "callback" ? JSON.stringify(payload) : undefined,
      headers: { cookie: request.headers.get("cookie") || "", "Content-Type": "application/json" },
      cache: "no-store", redirect: "manual", signal: AbortSignal.timeout(30_000),
    });
    for (const cookie of upstream.headers.getSetCookie()) headers.append("Set-Cookie", cookie);
    if (action === "qr" && upstream.ok) {
      const data = await upstream.json();
      headers.set("Content-Type", "application/json");
      return new Response(JSON.stringify({ loginUrl: data.loginUrl, expiresIn: data.expiresIn }), { headers });
    }
    const location = upstream.headers.get("location");
    if (location && upstream.status >= 300 && upstream.status < 400) {
      headers.set("Location", location);
      return new Response(null, { status: 303, headers });
    }
    headers.set("Location", `/local-login?error=${upstream.status === 503 ? "sso_not_configured" : "sso_unavailable"}`);
  } catch {
    headers.set("Location", "/local-login?error=sso_unavailable");
  }
  headers.append("Set-Cookie", "cognee_mind_map_state=; Path=/sso/mind-map; Max-Age=0; HttpOnly; Secure; SameSite=Lax");
  if (action === "qr") {
    headers.delete("Location");
    headers.set("Content-Type", "application/json");
    return new Response(JSON.stringify({ detail: "sso_unavailable" }), { status: 503, headers });
  }
  return new Response(null, { status: 303, headers });
}
