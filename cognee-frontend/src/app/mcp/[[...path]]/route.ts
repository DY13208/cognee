import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Same-origin MCP endpoint: browsers and IDE clients hit /mcp on the UI host
 * (e.g. http://192.168.1.30:3030/mcp), matching CPD's "URL follows the page"
 * behaviour. This handler forwards to the Streamable HTTP MCP server.
 */
function mcpUpstreamBase(): string {
  const configured =
    process.env.COGNEE_MCP_INTERNAL_URL?.trim() ||
    process.env.COGNEE_INTERNAL_MCP_URL?.trim();
  if (configured) return configured.replace(/\/$/, "");
  // Local `next dev` / host network: api-gateway publishes MCP at :8320/mcp.
  return "http://127.0.0.1:8320";
}

function buildUpstreamUrl(req: NextRequest, pathParts: string[] | undefined): string {
  const base = mcpUpstreamBase();
  const suffix = pathParts?.length ? `/${pathParts.map(encodeURIComponent).join("/")}` : "";
  const url = new URL(req.url);
  return `${base}/mcp${suffix}${url.search}`;
}

async function proxyMcp(req: NextRequest, pathParts?: string[]): Promise<Response> {
  const upstream = buildUpstreamUrl(req, pathParts);
  const headers = new Headers();
  // Preserve Host/Origin so MCP DNS-rebinding checks see the public host the
  // client used (LAN IP, localhost, or stillgroup domain) — not the docker
  // service name.
  const host = req.headers.get("host");
  if (host) headers.set("host", host);
  const origin = req.headers.get("origin");
  if (origin) headers.set("origin", origin);
  const accept = req.headers.get("accept");
  if (accept) headers.set("accept", accept);
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const authorization = req.headers.get("authorization");
  if (authorization) headers.set("authorization", authorization);
  const sessionId = req.headers.get("mcp-session-id");
  if (sessionId) headers.set("mcp-session-id", sessionId);

  const init: RequestInit = {
    method: req.method,
    headers,
    redirect: "manual",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.arrayBuffer();
  }

  let upstreamRes: Response;
  try {
    upstreamRes = await fetch(upstream, init);
  } catch (err) {
    const message = err instanceof Error ? err.message : "MCP upstream unreachable";
    return Response.json(
      { error: "MCP proxy failed", detail: message, upstream },
      { status: 502 },
    );
  }

  const outHeaders = new Headers();
  const passThrough = [
    "content-type",
    "mcp-session-id",
    "cache-control",
    "www-authenticate",
  ];
  for (const name of passThrough) {
    const value = upstreamRes.headers.get(name);
    if (value) outHeaders.set(name, value);
  }

  return new Response(upstreamRes.body, {
    status: upstreamRes.status,
    statusText: upstreamRes.statusText,
    headers: outHeaders,
  });
}

type RouteCtx = { params: Promise<{ path?: string[] }> };

export async function GET(req: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxyMcp(req, path);
}

export async function POST(req: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxyMcp(req, path);
}

export async function PUT(req: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxyMcp(req, path);
}

export async function PATCH(req: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxyMcp(req, path);
}

export async function DELETE(req: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxyMcp(req, path);
}

export async function OPTIONS(req: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxyMcp(req, path);
}
