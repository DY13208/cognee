import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import MobileMenuButton from "../MobileMenuButton";
import zhCN from "@/i18n/messages/zh-CN.json";

jest.mock("../NavbarContext", () => ({
  useNavbar: () => ({ isOpen: false, toggle: jest.fn() }),
}));

describe("MobileMenuButton copy", () => {
  it("exposes a catalogue-backed open-navigation label", () => {
    render(
      <NextIntlClientProvider locale="zh-CN" messages={zhCN}>
        <MobileMenuButton />
      </NextIntlClientProvider>,
    );

    expect(screen.getByRole("button", { name: "打开导航" })).toBeInTheDocument();
  });
});
