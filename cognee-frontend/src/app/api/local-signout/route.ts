import { NextResponse } from "next/server";
import { getServerBackendUrl } from "@/modules/config/serverRuntimeConfig";

export async function GET(request: Request) {
  const localApiUrl = getServerBackendUrl();
  const response = new NextResponse(null, {
    status: 303,
    headers: { Location: "/local-login", "Cache-Control": "no-store" },
  });
  // Call the local backend's logout endpoint to invalidate the session
  try {
    const upstream = await fetch(`${localApiUrl}/api/v1/auth/logout`, {
      method: "POST",
      headers: {
        cookie: request.headers.get("cookie") || "",
      },
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    for (const cookie of upstream.headers.getSetCookie()) response.headers.append("Set-Cookie", cookie);
  } catch {
    // Backend might be down — still clear cookies and redirect
  }

  // Clear both the current and legacy cookie even if the backend is unavailable.
  for (const name of ["auth_token", "fastapiusersauth"]) {
    response.cookies.set(name, "", { maxAge: 0, path: "/" });
  }
  response.cookies.set("codebuddy_oauth_state", "", { maxAge: 0, path: "/oauth" });
  return response;
}
