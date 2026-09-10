import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import InsufficientCreditsNotice from "../InsufficientCreditsNotice";
import zhCN from "@/i18n/messages/zh-CN.json";

jest.mock("@/modules/analytics", () => ({
  trackEvent: jest.fn(),
}));

function renderNotice(operation: string | null = "remember") {
  return render(
    <NextIntlClientProvider locale="zh-CN" messages={zhCN}>
      <InsufficientCreditsNotice isVisible operation={operation} onDismiss={() => undefined} />
    </NextIntlClientProvider>,
  );
}

describe("InsufficientCreditsNotice copy", () => {
  it("maps remember to the upload action in the notice", () => {
    renderNotice("remember");
    expect(screen.getByText("你上次上传失败——工作区余额过低。")).toBeInTheDocument();
    expect(screen.getByText("充值额度 →")).toBeInTheDocument();
    expect(screen.getByLabelText("关闭")).toBeInTheDocument();
  });

  it("maps search to the search action in the notice", () => {
    renderNotice("search");
    expect(screen.getByText("你上次检索失败——工作区余额过低。")).toBeInTheDocument();
  });
});
