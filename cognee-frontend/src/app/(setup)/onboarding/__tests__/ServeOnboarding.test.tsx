import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import ServeOnboarding from "../ServeOnboarding";
import zhCN from "@/i18n/messages/zh-CN.json";

const push = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

jest.mock("@/modules/tenant/TenantProvider", () => ({
  useCogniInstance: () => ({ cogniInstance: { fetch: jest.fn() }, isInitializing: false }),
}));

jest.mock("@/modules/users/UserContext", () => ({
  useUser: () => ({ markOnboardingComplete: jest.fn() }),
}));

jest.mock("@/modules/analytics", () => ({
  TrackPageView: () => null,
}));

jest.mock("../useOnboardingTrackEvent", () => ({
  useOnboardingTrackEvent: () => jest.fn(),
}));

describe("ServeOnboarding copy", () => {
  it("renders existing Setup.serve catalogue strings in Simplified Chinese", () => {
    render(
      <NextIntlClientProvider locale="zh-CN" messages={zhCN}>
        <ServeOnboarding />
      </NextIntlClientProvider>,
    );

    expect(screen.getByText("已连接到 Cognee Cloud")).toBeInTheDocument();
    expect(screen.getByText("连接已激活")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "继续" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "继续" }));
    expect(screen.getByText("SDK 快速开始")).toBeInTheDocument();
    expect(screen.getByText("存储数据")).toBeInTheDocument();
    expect(screen.getByText(/import cognee/)).toBeInTheDocument();
  });
});
