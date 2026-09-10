import { render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import { NextIntlClientProvider } from "next-intl";
import CreateModelModal from "../CreateModelModal";
import zhCN from "@/i18n/messages/zh-CN.json";

describe("CreateModelModal copy", () => {
  it("uses glossary-backed graph-model wording in Simplified Chinese", () => {
    render(
      <NextIntlClientProvider locale="zh-CN" messages={zhCN}>
        <MantineProvider>
          <CreateModelModal
            inferring={false}
            filesCount={0}
            onInfer={jest.fn()}
            onBlank={jest.fn()}
            onCancel={jest.fn()}
          />
        </MantineProvider>
      </NextIntlClientProvider>,
    );
    expect(screen.getByText("创建图谱模型")).toBeInTheDocument();
    expect(screen.getByText("此知识库中还没有文件")).toBeInTheDocument();
    expect(screen.getByText("从空白开始")).toBeInTheDocument();
  });
});
