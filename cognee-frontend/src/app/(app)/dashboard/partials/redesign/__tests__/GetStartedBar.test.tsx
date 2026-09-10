import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { GetStartedBar } from "../GetStartedBar";
import zhCN from "@/i18n/messages/zh-CN.json";

function renderBar(connectors = 5) {
  return render(
    <NextIntlClientProvider locale="zh-CN" messages={zhCN}>
      <GetStartedBar subtitle="连接智能体" connectors={connectors}>
        <div>cards</div>
      </GetStartedBar>
    </NextIntlClientProvider>,
  );
}

describe("GetStartedBar copy", () => {
  it("shows get-started chrome from the dashboard catalogue", () => {
    renderBar();
    expect(screen.getByText("开始使用")).toBeInTheDocument();
    expect(screen.getByText("5 个连接器")).toBeInTheDocument();
    expect(screen.getByText("展开 ▾")).toBeInTheDocument();
  });

  it("toggles to the collapse label when expanded", () => {
    renderBar(1);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("收起 ▴")).toBeInTheDocument();
    expect(screen.getByText("1 个连接器")).toBeInTheDocument();
  });
});
