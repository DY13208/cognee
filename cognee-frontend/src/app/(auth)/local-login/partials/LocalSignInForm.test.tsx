import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import LocalSignInForm from "./LocalSignInForm";

jest.mock("@/modules/users/getLocalApiUrl", () => ({ getLocalApiUrl: () => "http://backend" }));

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", { writable: true, value: jest.fn().mockImplementation((query) => ({
    matches: false, media: query, onchange: null, addListener: jest.fn(), removeListener: jest.fn(),
    addEventListener: jest.fn(), removeEventListener: jest.fn(), dispatchEvent: jest.fn(),
  })) });
  global.ResizeObserver = class {
    observe() {} unobserve() {} disconnect() {}
  };
});
afterEach(() => { jest.restoreAllMocks(); jest.useRealTimers(); });
const qrResponse = () => new Response(JSON.stringify({ loginUrl: "https://open.work.weixin.qq.com/wwopen/sso/qrConnect?state=test", expiresIn: 600 }));
function show(enabled = true) {
  return render(<MantineProvider><LocalSignInForm mindMapSsoEnabled={enabled} /></MantineProvider>);
}

it("defaults to QR, cancels it on password switch, and supports returning to QR", async () => {
  const fetchSpy = jest.spyOn(global, "fetch").mockImplementation(async () => qrResponse());
  show();
  await screen.findByTitle("企业微信扫码登录");
  expect(screen.queryByLabelText(/^邮箱/)).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Login WorkBuddy" })).toHaveAttribute("href", "/oauth/login");
  const signal = fetchSpy.mock.calls[0][1]?.signal;
  fireEvent.click(screen.getByRole("button", { name: "账号密码登录" }));
  expect(screen.getByLabelText(/^邮箱/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Login WorkBuddy" })).toHaveAttribute("href", "/oauth/login");
  expect(screen.queryByTitle("企业微信扫码登录")).not.toBeInTheDocument();
  expect(signal?.aborted).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "返回企业微信扫码" }));
  await screen.findByTitle("企业微信扫码登录");
  expect(fetchSpy).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("link", { name: "Login WorkBuddy" })).toHaveAttribute("href", "/oauth/login");
});

it("offers retry and password login when QR initialization fails", async () => {
  const fetchSpy = jest.spyOn(global, "fetch").mockResolvedValueOnce(new Response("unavailable", { status: 503 })).mockImplementation(async () => qrResponse());
  show();
  expect(await screen.findByRole("alert")).toHaveTextContent("二维码加载失败");
  expect(screen.getByRole("link", { name: "Login WorkBuddy" })).toHaveAttribute("href", "/oauth/login");
  fireEvent.click(screen.getByRole("button", { name: "刷新二维码" }));
  await screen.findByTitle("企业微信扫码登录");
  expect(fetchSpy).toHaveBeenCalledTimes(2);
});

it("refreshes an expired QR instead of retaining expired state", async () => {
  jest.useFakeTimers();
  const fetchSpy = jest.spyOn(global, "fetch").mockImplementation(async () => qrResponse());
  show();
  await screen.findByTitle("企业微信扫码登录");
  await act(async () => { jest.advanceTimersByTime(600_000); });
  await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
});

it("keeps password login usable when SSO is disabled and reports invalid credentials", async () => {
  const fetchSpy = jest.spyOn(global, "fetch").mockResolvedValue(new Response("", { status: 400 }));
  show(false);
  expect(screen.getByRole("link", { name: "Login WorkBuddy" })).toHaveAttribute("href", "/oauth/login");
  fireEvent.change(screen.getByLabelText(/^邮箱/), { target: { value: "existing@example.com" } });
  fireEvent.change(screen.getByLabelText(/^密码/), { target: { value: "fixture-password" } });
  fireEvent.click(screen.getByRole("button", { name: "账号密码登录" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("邮箱或密码不正确");
  expect(fetchSpy.mock.calls[0][0]).toBe("http://backend/api/v1/auth/login");
  expect(fetchSpy.mock.calls[0][1]?.body).toBe("username=existing%40example.com&password=fixture-password");
});
