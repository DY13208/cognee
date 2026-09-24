import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { CogneeInstance } from "@/modules/instances/types";
import CPDTreePanel from "../CPDTreePanel";
import { BusinessLanguageProvider, useBusinessLanguage } from "../BusinessLanguageContext";

const mockFetch = jest.fn();
const instance = {
  name: "CloudCognee",
  instanceId: "inst-1",
  fetch: mockFetch,
} as CogneeInstance;

function renderPanel() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <CPDTreePanel instance={instance} datasetId="dataset-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => mockFetch.mockReset());

function LanguageButtons() {
  const { setLanguage } = useBusinessLanguage();
  return <button type="button" onClick={() => setLanguage("en")}>English</button>;
}

it("shows the entry only for a dataset with a company tree and opens on click", async () => {
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({
      rootId: "root",
      nodes: [{ id: "root", name: "公司运营", kind: "goal" }],
      edges: [],
      complete: true,
    }),
  });

  renderPanel();
  expect(screen.queryByRole("group", { name: "视图切换" })).not.toBeInTheDocument();
  const button = await screen.findByRole("button", { name: "公司目标树" });
  const switcher = screen.getByRole("group", { name: "视图切换" });
  expect(screen.getByRole("button", { name: "关系图" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.queryByRole("region", { name: "公司目标树" })).not.toBeInTheDocument();

  fireEvent.click(button);
  expect(screen.getByRole("group", { name: "视图切换" })).toBe(switcher);
  expect(screen.getByRole("region", { name: "公司目标树" })).toBeInTheDocument();
  expect(button).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "关系图" }));
  expect(screen.getByRole("group", { name: "视图切换" })).toBe(switcher);
  expect(screen.queryByRole("region", { name: "公司目标树" })).not.toBeInTheDocument();
});

it("uses the goal directory to expand and select a primary branch", async () => {
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({
      rootId: "root",
      nodes: [
        { id: "root", name: "公司运营", kind: "goal" },
        { id: "branch", name: "公司利润分", kind: "goal" },
        { id: "child", name: "利润目标", kind: "goal" },
      ],
      edges: [
        { source: "root", target: "branch", label: "has_subgoal" },
        { source: "branch", target: "child", label: "has_subgoal" },
      ],
      complete: true,
    }),
  });

  renderPanel();
  fireEvent.click(await screen.findByRole("button", { name: "公司目标树" }));
  const directory = screen.getByRole("navigation", { name: "目标目录" });
  expect(directory).toHaveTextContent("1 个分支");
  fireEvent.click(directory.querySelector<HTMLButtonElement>(".bv-company-outline-child")!);
  const branch = screen.getByRole("treeitem", { name: /公司利润分/ });
  expect(branch).toHaveAttribute("aria-expanded", "true");
  expect(branch).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("heading", { name: "公司利润分" })).toBeInTheDocument();
});

it("switches goal tree controls and descriptions into English", async () => {
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({
      rootId: "root",
      nodes: [{ id: "root", name: "公司运营", kind: "goal" }],
      edges: [],
      complete: true,
    }),
  });
  const client = new QueryClient();
  render(
    <BusinessLanguageProvider>
      <QueryClientProvider client={client}>
        <LanguageButtons />
        <CPDTreePanel instance={instance} datasetId="dataset-1" />
      </QueryClientProvider>
    </BusinessLanguageProvider>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "English" }));
  fireEvent.click(screen.getByRole("button", { name: "Company goal tree" }));
  expect(screen.getByRole("navigation", { name: "Goal outline" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Import linked maps" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "公司运营" })).toBeInTheDocument();
});

it("does not show the entry when the backend reports an empty tree", async () => {
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ nodes: [], edges: [], missing: ["empty"] }),
  });

  renderPanel();
  await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
  expect(screen.queryByRole("group", { name: "视图切换" })).not.toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "公司目标树" })).not.toBeInTheDocument();
});

it("offers retry when checking the tree fails", async () => {
  mockFetch.mockRejectedValueOnce(new Error("Network unavailable"));
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ nodes: [], edges: [], missing: ["empty"] }),
  });

  renderPanel();
  fireEvent.click(await screen.findByRole("button", { name: "目标树读取失败，重试" }));
  await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(2));
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "目标树读取失败，重试" })).not.toBeInTheDocument(),
  );
});
