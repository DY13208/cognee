import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import SetupConnectorCard from "../SetupConnectorCard";
import type { SetupConnectorCfg } from "@/modules/integrations/types";
import zhCN from "@/i18n/messages/zh-CN.json";

const card: SetupConnectorCfg = {
  key: "claude-code",
  name: "Claude Code",
  cta: "Connect via plugin",
  description: "Give Claude Code persistent memory across sessions.",
  icon: <span>icon</span>,
  buildSteps: () => [],
};

function renderCard(props: { isConnected: boolean; hasSignal?: boolean }) {
  return render(
    <NextIntlClientProvider locale="zh-CN" messages={zhCN}>
      <SetupConnectorCard
        card={card}
        isActive={false}
        hasSignal={props.hasSignal ?? true}
        isConnected={props.isConnected}
        onOpen={() => undefined}
      />
    </NextIntlClientProvider>,
  );
}

describe("SetupConnectorCard copy", () => {
  it("shows the connected badge from the integrations catalogue", () => {
    renderCard({ isConnected: true });
    expect(screen.getByText("已连接")).toBeInTheDocument();
    expect(screen.getByText("让 Claude Code 跨会话拥有持久记忆。")).toBeInTheDocument();
    expect(screen.getByText("通过插件连接")).toBeInTheDocument();
  });

  it("shows the not-connected badge from the integrations catalogue", () => {
    renderCard({ isConnected: false });
    expect(screen.getByText("尚未连接")).toBeInTheDocument();
  });
});
