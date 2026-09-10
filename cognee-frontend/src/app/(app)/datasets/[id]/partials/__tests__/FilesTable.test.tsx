import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ComponentProps } from "react";
import FilesTable from "../FilesTable";
import zhCN from "@/i18n/messages/zh-CN.json";
import en from "@/i18n/messages/en.json";

function renderTable(
  locale: "zh-CN" | "en",
  props: Partial<ComponentProps<typeof FilesTable>> = {},
) {
  const messages = locale === "zh-CN" ? zhCN : en;
  return render(
    <NextIntlClientProvider locale={locale} messages={messages}>
      <FilesTable
        files={[]}
        memorySessionIds={{}}
        search=""
        loadError={false}
        onDelete={jest.fn()}
        onUploadClick={jest.fn()}
        onRetry={jest.fn()}
        {...props}
      />
    </NextIntlClientProvider>,
  );
}

describe("FilesTable copy", () => {
  it("renders Simplified Chinese empty and error states from the catalogue", () => {
    renderTable("zh-CN");
    expect(screen.getByText("还没有文件")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "上传文件" })).toBeInTheDocument();
  });

  it("renders the English empty state when the locale is English", () => {
    renderTable("en");
    expect(screen.getByText("No files yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload files" })).toBeInTheDocument();
  });

  it("keeps a safe retry path when files fail to load", () => {
    const onRetry = jest.fn();
    renderTable("zh-CN", { loadError: true, onRetry });
    expect(screen.getByText("无法加载文件")).toBeInTheDocument();
    expect(screen.getByText("连接服务器时出现问题。您的文件仍安全保存，请重试。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
