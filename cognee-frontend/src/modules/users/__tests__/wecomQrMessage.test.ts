import { wecomCallbackFromMessage } from "../wecomQrMessage";

const frame = {} as Window;
const callback = "https://xx.stillgroup.net:8989/api/auth/wecom/callback";
const qr = "https://open.work.weixin.qq.com/wwopen/sso/qrConnect?" + new URLSearchParams({ redirect_uri: callback, state: "browser-state" });
const valid = { source: frame, origin: "https://open.work.weixin.qq.com", data: callback + "?code=once&state=browser-state" };

it("accepts the original callback only from the current QR frame", () => {
  expect(wecomCallbackFromMessage(valid, frame, qr)).toBe(valid.data);
});

it.each([
  { ...valid, source: {} as Window },
  { ...valid, origin: "https://open.work.weixin.qq.com.evil.invalid" },
  { ...valid, data: "https://evil.invalid/api/auth/wecom/callback?state=browser-state" },
  { ...valid, data: callback + "?state=other-browser" },
  { ...valid, data: callback.replace("/callback", "/logout") + "?state=browser-state" },
  { ...valid, data: { url: valid.data } },
  { ...valid, data: callback + "?state=browser-state#fragment" },
])("ignores spoofed or unrelated iframe messages", (event) => {
  expect(wecomCallbackFromMessage(event, frame, qr)).toBeNull();
});
