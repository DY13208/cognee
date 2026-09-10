import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import CustomAppShellNavbar from "../CustomAppShellNavbar";
import zhCN from "@/i18n/messages/zh-CN.json";

const navbarState = {
  isOpen: true,
  close: jest.fn(),
  collapsed: false,
  toggleCollapsed: jest.fn(),
};

jest.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ refresh: jest.fn() }),
}));

jest.mock("../../NavbarContext", () => ({
  useNavbar: () => navbarState,
}));

jest.mock("@/modules/tenant/TenantContext", () => ({
  useTenant: () => ({ tenantReady: true }),
}));

jest.mock("@/utils/isCloudEnvironment", () => ({
  __esModule: true,
  default: () => false,
}));

describe("CustomAppShellNavbar copy", () => {
  beforeEach(() => {
    navbarState.isOpen = true;
    navbarState.collapsed = false;
  });

  it("renders glossary-backed nav labels and sidebar a11y names in Simplified Chinese", () => {
    render(
      <NextIntlClientProvider locale="zh-CN" messages={zhCN}>
        <CustomAppShellNavbar />
      </NextIntlClientProvider>,
    );

    expect(screen.getByText("数据")).toBeInTheDocument();
    expect(screen.getByText("探索")).toBeInTheDocument();
    expect(screen.getByText("连接")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "知识库" })).toHaveAttribute("href", "/datasets");
    expect(screen.getByRole("link", { name: "检索" })).toHaveAttribute("href", "/search");
    expect(screen.getByRole("link", { name: "会话" })).toHaveAttribute("href", "/sessions");
    expect(screen.getByRole("link", { name: "知识图谱" })).toHaveAttribute("href", "/knowledge-graph");
    expect(screen.getByRole("link", { name: "API 密钥" })).toHaveAttribute("href", "/api-keys");
    expect(screen.getByRole("button", { name: "收起侧栏" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "关闭导航" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "提供反馈" })).toBeInTheDocument();
  });
});
