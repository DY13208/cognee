import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import IntegrationsPage from "../IntegrationsPage";
import zhCN from "@/i18n/messages/zh-CN.json";

jest.mock("@/modules/analytics", () => ({
  TrackPageView: () => null,
}));

jest.mock("../partials/useAgentConnectionStatus", () => ({
  useAgentConnectionStatus: () => ({}),
}));

jest.mock("../partials/SetupConnectorSection", () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock("../partials/DataSourceSection", () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock("../partials/MoreDataSourcesSection", () => ({
  __esModule: true,
  default: () => null,
}));

describe("IntegrationsPage copy", () => {
  it("uses glossary-backed agents and automation wording in Simplified Chinese", () => {
    render(
      <NextIntlClientProvider locale="zh-CN" messages={zhCN}>
        <IntegrationsPage />
      </NextIntlClientProvider>,
    );

    expect(screen.getByRole("heading", { name: "智能体" })).toBeInTheDocument();
    expect(screen.getByText("将 AI 智能体和编程工具连接到 Cognee，以获得持久记忆。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "自动化平台" })).toBeInTheDocument();
    expect(screen.getByText("通过 MCP 让自动化工作流访问 Cognee 记忆。")).toBeInTheDocument();
  });
});
