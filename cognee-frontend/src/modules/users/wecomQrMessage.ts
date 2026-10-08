/** Accept only the embedded provider frame and mind-map's original callback. */
export function wecomCallbackFromMessage(
  event: Pick<MessageEvent, "origin" | "source" | "data">,
  frameWindow: Window | null,
  loginUrl: string,
): string | null {
  if (!frameWindow || event.source !== frameWindow || typeof event.data !== "string") return null;
  try {
    const qr = new URL(loginUrl);
    const callback = new URL(qr.searchParams.get("redirect_uri") || "");
    const target = new URL(event.data);
    if (event.origin !== qr.origin || callback.protocol !== "https:"
      || target.origin !== callback.origin || target.pathname !== callback.pathname
      || callback.pathname !== "/api/auth/wecom/callback"
      || target.username || target.password || target.hash
      || !qr.searchParams.get("state") || target.searchParams.get("state") !== qr.searchParams.get("state")) return null;
    return target.href;
  } catch {
    return null;
  }
}
