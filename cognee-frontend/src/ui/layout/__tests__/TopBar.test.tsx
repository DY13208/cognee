import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import TopBar from "../TopBar";
import zhCN from "@/i18n/messages/zh-CN.json";

let pathname = "/search";

jest.mock("next/navigation", () => ({
  usePathname: () => pathname,
}));

jest.mock("next/image", () => ({
  __esModule: true,
  default: (props: { alt: string }) => <img alt={props.alt} />,
}));

jest.mock("../HelpMenu", () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock("../ProfileMenu", () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock("@/modules/users/useCurrentUser", () => ({
  useCurrentUser: () => ({ data: undefined }),
}));

jest.mock("@/modules/users/getLocalUser", () => ({
  __esModule: true,
  default: () => Promise.resolve(undefined),
}));

jest.mock("@/utils/isCloudEnvironment", () => ({
  __esModule: true,
  default: () => false,
}));

jest.mock("../FilterContext", () => ({
  useFilter: () => ({
    workspace: { id: "ws-1", name: "Acme", initial: "A", color: "#6510F4", type: "organization" },
    workspaces: [{ id: "ws-1", name: "Acme", initial: "A", color: "#6510F4", type: "organization" }],
    setWorkspace: jest.fn(),
  }),
}));

jest.mock("@/modules/tenant/TenantContext", () => ({
  useTenant: () => ({
    requestCreateWorkspace: jest.fn(),
    availableTenants: [],
  }),
}));

describe("TopBar copy", () => {
  it("uses glossary-backed breadcrumb labels in Simplified Chinese", () => {
    pathname = "/search";
    render(
      <NextIntlClientProvider locale="zh-CN" messages={zhCN}>
        <TopBar />
      </NextIntlClientProvider>,
    );
    expect(screen.getByText("检索")).toBeInTheDocument();
  });

  it("labels a dataset detail trail as knowledge base documents", () => {
    pathname = "/datasets/abc-123";
    render(
      <NextIntlClientProvider locale="zh-CN" messages={zhCN}>
        <TopBar />
      </NextIntlClientProvider>,
    );
    expect(screen.getByRole("link", { name: "知识库" })).toHaveAttribute("href", "/datasets");
    expect(screen.getByText("文档")).toBeInTheDocument();
  });
});
