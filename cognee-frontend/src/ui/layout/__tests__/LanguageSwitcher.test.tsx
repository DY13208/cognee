import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import LanguageSwitcher from "@/ui/layout/LanguageSwitcher";

const refresh = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

const messages = { LanguageSwitcher: { label: "语言", english: "English", chinese: "简体中文" } };

describe("LanguageSwitcher", () => {
  beforeEach(() => {
    document.cookie = "cognee_locale=; Path=/; Max-Age=0";
    document.documentElement.lang = "zh-CN";
  });

  it("stores the selected locale and refreshes the current route", () => {
    render(<NextIntlClientProvider locale="zh-CN" messages={messages}><LanguageSwitcher /></NextIntlClientProvider>);
    fireEvent.change(screen.getByLabelText("语言"), { target: { value: "en" } });
    expect(document.cookie).toContain("cognee_locale=en");
    expect(document.documentElement.lang).toBe("en");
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});
