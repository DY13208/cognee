/** @jest-environment node */
import { isMindMapSsoEnabled, proxyMindMapSso } from "../mindMapSsoProxy";

jest.mock("@/modules/config/serverRuntimeConfig", () => ({
  getServerBackendUrl: () => "http://cognee:8000",
}));

describe("mind-map SSO proxy", () => {
  afterEach(() => jest.restoreAllMocks());

  it("forwards only code/state and preserves session and browser cookies", async () => {
    const headers = new Headers({ location: "https://xx.stillgroup.net:3030/" });
    const upstream = new Response(null, { status: 303, headers });
    Object.defineProperty(upstream.headers, "getSetCookie", { value: () => [
      "auth_token=session; Path=/; Secure; HttpOnly",
      "cognee_mind_map_state=; Path=/sso/mind-map; Max-Age=0",
    ] });
    const fetchSpy = jest.spyOn(global, "fetch").mockResolvedValue(upstream);
    const response = await proxyMindMapSso(new Request(
      "https://xx.stillgroup.net:3030/sso/mind-map/callback?code=once&state=browser&next=https://evil.invalid",
      { headers: { cookie: "cognee_mind_map_state=signed" } },
    ), "callback");
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toBe("http://cognee:8000/api/v1/auth/mind-map/callback");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ code: "once", state: "browser" });
    expect(init?.headers).toEqual({ cookie: "cognee_mind_map_state=signed", "Content-Type": "application/json" });
    expect(response.headers.get("set-cookie")).toContain("auth_token=session");
    expect(response.headers.get("set-cookie")).toContain("cognee_mind_map_state=");
    expect(response.headers.get("location")).toBe("https://xx.stillgroup.net:3030/");
    expect(response.headers.get("referrer-policy")).toBe("no-referrer");
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it.each([503, 500, 401])("uses a safe retry page for HTTP %s", async (status) => {
    const upstream = new Response("sensitive backend detail", { status });
    Object.defineProperty(upstream.headers, "getSetCookie", { value: () => [] });
    jest.spyOn(global, "fetch").mockResolvedValue(upstream);
    const response = await proxyMindMapSso(new Request("https://xx.stillgroup.net:3030/sso/mind-map/login"), "login");
    expect(response.headers.get("location")).toBe(`/local-login?error=${status === 503 ? "sso_not_configured" : "sso_unavailable"}`);
    expect(await response.text()).toBe("");
    expect(response.headers.get("set-cookie")).toContain("cognee_mind_map_state=;");
    expect(response.headers.get("set-cookie")).toContain("Max-Age=0");
  });

  it("forwards a WeCom failure and state without arbitrary redirect parameters", async () => {
    const upstream = new Response(null, { status: 303, headers: { location: "/local-login?error=sso_wecom_failed" } });
    Object.defineProperty(upstream.headers, "getSetCookie", { value: () => [] });
    const spy = jest.spyOn(global, "fetch").mockResolvedValue(upstream);
    await proxyMindMapSso(new Request(
      "https://xx.stillgroup.net:3030/sso/mind-map/callback?error=wecom_login_failed&state=browser&next=https://evil.invalid",
    ), "callback");
    expect(JSON.parse(spy.mock.calls[0][1]?.body as string)).toEqual({ error: "wecom_login_failed", state: "browser" });
  });

  it("shows SSO only when backend says enabled, and fails safely on an outage", async () => {
    const spy = jest.spyOn(global, "fetch").mockResolvedValue(new Response('{"enabled":true}'));
    expect(await isMindMapSsoEnabled()).toBe(true);
    spy.mockRejectedValue(new Error("private detail"));
    expect(await isMindMapSsoEnabled()).toBe(false);
    const response = await proxyMindMapSso(new Request("https://xx.stillgroup.net:3030/sso/mind-map/login"), "login");
    expect(response.headers.get("location")).toBe("/local-login?error=sso_unavailable");
    expect(response.headers.get("set-cookie")).toContain("cognee_mind_map_state=;");
    expect(response.headers.get("set-cookie")).toContain("Max-Age=0");
  });
});
