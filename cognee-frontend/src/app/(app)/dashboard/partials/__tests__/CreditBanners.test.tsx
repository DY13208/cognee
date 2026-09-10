import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { CreditBanners } from "../CreditBanners";
import zhCN from "@/i18n/messages/zh-CN.json";

type BannerProps = {
  creditsSpentPct?: number | null;
  creditsRemainingUsd?: number | null;
  showCreditPctBanner?: boolean;
  showLowBalanceBanner?: boolean;
  showVoucherBanner?: boolean;
  isOwner?: boolean;
};

function renderBanner(props: BannerProps = {}) {
  return render(
    <NextIntlClientProvider locale="zh-CN" messages={zhCN}>
      <CreditBanners
        creditsSpentPct={null}
        creditsRemainingUsd={null}
        showCreditPctBanner={false}
        showLowBalanceBanner={false}
        showVoucherBanner={false}
        onDismiss={() => undefined}
        isOwner
        {...props}
      />
    </NextIntlClientProvider>,
  );
}

describe("CreditBanners copy", () => {
  it("shows the exhausted-credits banner from the dashboard catalogue", () => {
    renderBanner({ showCreditPctBanner: true, creditsSpentPct: 100 });
    expect(screen.getByText("工作区额度已用尽。智能体请求可能会失败。")).toBeInTheDocument();
    expect(screen.getByText("充值额度 →")).toBeInTheDocument();
    expect(screen.getByLabelText("关闭")).toBeInTheDocument();
  });

  it("interpolates the used-credits percentage", () => {
    renderBanner({ showCreditPctBanner: true, creditsSpentPct: 82 });
    expect(screen.getByText("工作区已使用 82% 的可用额度。")).toBeInTheDocument();
  });

  it("formats a remaining USD balance without translating the amount", () => {
    renderBanner({ showLowBalanceBanner: true, creditsRemainingUsd: 1.5 });
    expect(screen.getByText("工作区额度余额为 $1.50。智能体请求可能会失败。")).toBeInTheDocument();
  });

  it("falls back to the below-one label when no USD remainder is known", () => {
    renderBanner({ showLowBalanceBanner: true, creditsRemainingUsd: null });
    expect(screen.getByText("工作区额度余额为 低于 $1。智能体请求可能会失败。")).toBeInTheDocument();
  });

  it("asks a non-owner to have the workspace owner top up", () => {
    renderBanner({ showCreditPctBanner: true, creditsSpentPct: 100, isOwner: false });
    expect(screen.getByText("请让工作区所有者充值。")).toBeInTheDocument();
  });

  it("shows the voucher banner from the dashboard catalogue", () => {
    renderBanner({ showVoucherBanner: true });
    expect(screen.getByText("有代金券？在这里兑换。")).toBeInTheDocument();
    expect(screen.getByText("兑换代金券 →")).toBeInTheDocument();
  });
});
