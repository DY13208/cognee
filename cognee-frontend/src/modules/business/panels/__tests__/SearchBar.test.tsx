import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import SearchBar from "../SearchBar";
import type { CogneeInstance } from "@/modules/instances/types";
import zhCN from "@/i18n/messages/zh-CN.json";

const searchDataset = jest.fn();

jest.mock("@/modules/datasets/searchDataset", () => ({
  __esModule: true,
  default: (...args: unknown[]) => searchDataset(...args),
}));

jest.mock("@/utils/monitoring", () => ({
  captureException: jest.fn(),
}));

const instance = { name: "CloudCognee", instanceId: "test", fetch: jest.fn() } as unknown as CogneeInstance;

function renderBar(onAnswer = jest.fn()) {
  render(
    <NextIntlClientProvider locale="zh-CN" messages={zhCN}>
      <SearchBar
        cogniInstance={instance}
        activeDatasetId="ds-1"
        onAnswer={onAnswer}
        entities={[]}
        onPickEntity={() => undefined}
      />
    </NextIntlClientProvider>,
  );
  return onAnswer;
}

describe("SearchBar copy", () => {
  it("uses the knowledge-graph placeholder", () => {
    renderBar();
    expect(screen.getByPlaceholderText("查找记录或提问…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "提问" })).toBeInTheDocument();
  });

  it("offers the translated ask-query row for a typed question", () => {
    renderBar();
    fireEvent.change(screen.getByPlaceholderText("查找记录或提问…"), { target: { value: "who?" } });
    expect(screen.getByRole("button", { name: /提问："who\?"/ })).toBeInTheDocument();
  });

  it("returns the catalogue no-answer string when search is empty", async () => {
    searchDataset.mockResolvedValueOnce([{ search_result: [] }]);
    const onAnswer = renderBar();
    fireEvent.change(screen.getByPlaceholderText("查找记录或提问…"), { target: { value: "who?" } });
    fireEvent.keyDown(screen.getByPlaceholderText("查找记录或提问…"), { key: "Enter" });
    await waitFor(() => {
      expect(onAnswer).toHaveBeenCalledWith("who?", "未找到答案。");
    });
  });

  it("returns the catalogue search-failed string when search throws", async () => {
    searchDataset.mockRejectedValueOnce(new Error("boom"));
    const onAnswer = renderBar();
    fireEvent.change(screen.getByPlaceholderText("查找记录或提问…"), { target: { value: "who?" } });
    fireEvent.keyDown(screen.getByPlaceholderText("查找记录或提问…"), { key: "Enter" });
    await waitFor(() => {
      expect(onAnswer).toHaveBeenCalledWith("who?", "检索失败，请重试。");
    });
  });
});
