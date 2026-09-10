import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import ApiKeysPage from "../ApiKeysPage";
import zhCN from "@/i18n/messages/zh-CN.json";

jest.mock("@/modules/tenant/TenantProvider", () => ({
  useCogniInstance: () => ({
    cogniInstance: {},
    serviceUrl: "http://localhost:8000",
    isInitializing: false,
  }),
  useTenant: () => ({ tenant: null, hasAccess: true, tenantReady: true }),
}));

jest.mock("@/utils", () => ({
  isCloudEnvironment: () => false,
}));

jest.mock("@/modules/analytics", () => ({
  TrackPageView: () => null,
  trackEvent: jest.fn(),
}));

describe("ApiKeysPage copy", () => {
  it("renders glossary-backed API key wording in Simplified Chinese", async () => {
    render(
      <NextIntlClientProvider locale="zh-CN" messages={zhCN}>
        <ApiKeysPage />
      </NextIntlClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("还没有 API 密钥")).toBeInTheDocument();
    });
    expect(screen.getByRole("heading", { name: "API 密钥" })).toBeInTheDocument();
    expect(screen.getByText("管理用于以编程方式访问 Cognee API 的密钥。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建新密钥" })).toBeInTheDocument();
    expect(screen.getByText("连接详情")).toBeInTheDocument();
    expect(screen.getByText("租户 ID")).toBeInTheDocument();
    expect(screen.getByText("未分配（本地模式）")).toBeInTheDocument();
    expect(screen.getByText("创建密钥后即可连接智能体，或以编程方式调用 API。")).toBeInTheDocument();
  });

  it("opens the create-key dialog with catalogue copy", async () => {
    render(
      <NextIntlClientProvider locale="zh-CN" messages={zhCN}>
        <ApiKeysPage />
      </NextIntlClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("还没有 API 密钥")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "创建新密钥" }));
    expect(screen.getByRole("heading", { name: "创建 API 密钥" })).toBeInTheDocument();
    expect(screen.getByText("为密钥命名，以便日后识别。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "取消" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建" })).toBeInTheDocument();
  });
});
