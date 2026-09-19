/** @jest-environment node */
import { proxyCodeBuddy } from "../codebuddyProxy";

jest.mock("@/modules/config/serverRuntimeConfig", () => ({
  getServerBackendUrl: () => "http://cognee:8000",
}));

describe("CodeBuddy server proxy", () => {
  it.each([
    [502, "Bad Gateway", "provider_unavailable"],
    [500, "Internal error", "provider_unavailable"],
    [503, JSON.stringify({ detail: "WorkBuddy login is not configured" }), "not_configured"],
  ])("classifies upstream status %s without exposing its body", async (status, body, errorCode) => {
    const upstream = new Response(body as string, { status: status as number });
    Object.defineProperty(upstream.headers, "getSetCookie", { value: () => [] });
    const fetchSpy = jest.spyOn(global, "fetch").mockResolvedValue(upstream);
    const logSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
    try {
      const response = await proxyCodeBuddy(new Request("https://127.0.0.1:3030/oauth/login"), "login");
      expect(response.headers.get("location")).toBe(`/local-login?error=${errorCode}`);
      expect(await response.text()).toBe("");
      expect(logSpy).toHaveBeenCalledWith("WorkBuddy OAuth proxy failed", {
        action: "login", status, errorCode,
      });
    } finally {
      fetchSpy.mockRestore();
      logSpy.mockRestore();
    }
  });
  it("forwards callback fields in a body and carries every cookie back to the browser", async () => {
    const headers = new Headers({ location: "https://127.0.0.1:3030/" });
    headers.append("Set-Cookie", "auth_token=session; Path=/; Secure; HttpOnly");
    headers.append("Set-Cookie", "codebuddy_oauth_state=; Path=/oauth; Max-Age=0");
    const upstream = new Response(null, { status: 303, headers });
    // jest-fetch-mock uses node-fetch Headers, unlike Node 22's production Headers.
    Object.defineProperty(upstream.headers, "getSetCookie", { value: () => [
      "auth_token=session; Path=/; Secure; HttpOnly",
      "codebuddy_oauth_state=; Path=/oauth; Max-Age=0",
    ] });
    const fetchSpy = jest.spyOn(global, "fetch").mockResolvedValue(upstream);
    const response = await proxyCodeBuddy(new Request(
      "https://127.0.0.1:3030/oauth/callback?code=one-time-code&state=browser-state&next=https://evil.invalid",
      { headers: { cookie: "codebuddy_oauth_state=signed-state" } },
    ), "callback");
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toBe("http://cognee:8000/api/v1/auth/codebuddy/callback");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ code: "one-time-code", state: "browser-state" });
    expect(init?.redirect).toBe("manual");
    expect(response.headers.get("set-cookie")).toContain("auth_token=session");
    expect(response.headers.get("set-cookie")).toContain("codebuddy_oauth_state=");
    expect(response.headers.get("location")).toBe("https://127.0.0.1:3030/");
    expect(response.headers.get("cache-control")).toBe("no-store");
    fetchSpy.mockRestore();
  });

  it("uses a safe retry page when the backend is unavailable", async () => {
    const fetchSpy = jest.spyOn(global, "fetch").mockRejectedValue(new Error("private backend error"));
    const response = await proxyCodeBuddy(new Request("https://127.0.0.1:3030/oauth/login"), "login");
    expect(response.headers.get("location")).toBe("/local-login?error=provider_unavailable");
    expect(await response.text()).not.toContain("private backend error");
    fetchSpy.mockRestore();
  });
});
