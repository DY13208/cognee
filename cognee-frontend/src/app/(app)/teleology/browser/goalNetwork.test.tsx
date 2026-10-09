import { act, fireEvent, render, screen } from "@testing-library/react";
import { GoalNetworkPresentation } from "./GoalNetworkView";
import { businessName, currentNetwork, layoutNetwork, NETWORK_TYPES, NODE_LABELS, RELATION_LABELS } from "./goalNetwork";
import { buildDerivedGoalTree } from "./derivedGoalTree";
import { fitCanvasBounds } from "./fitCanvas";
import type { GoalCandidate, GoalModelView, GoalNetworkLoop, GoalTeleologyItem } from "@/modules/teleology/teleologyApi";

const nodes = NETWORK_TYPES.map((node_type, i) => ({ id: `n${i}`, name: `${i ? "C2 " : "G1 "}${NODE_LABELS[node_type]}业务`, node_type, status: "confirmed", evidence: [] } as unknown as GoalCandidate));
const edge = (relationship: string, source = "n0", target = "n2") => ({ id: relationship, relationship, source, target, status: "confirmed" } as GoalTeleologyItem);
const model = { candidates: nodes, relations: Object.keys(RELATION_LABELS).map(r => r === "drives" ? edge(r, "n5", "n0") : r === "enables" ? edge(r, "n1", "n0") : edge(r)), hierarchy: [] } as unknown as GoalModelView;
const loop = { loop_id: "server-loop", nodes: ["n0", "n2"], edges: [edge("advances"), edge("blocks", "n2", "n0")], negative_edge_count: 1, loop_type: "Balancing", confidence: .9, conditions: [] } as GoalNetworkLoop;

test("fit centers offset cards within pixel padding across canvas aspect ratios", () => {
  const cards = [{ x: -800, y: 500, width: 240, height: 250 }, { x: 1800, y: -500, width: 240, height: 160 }];
  for (const canvas of [{ width: 1000, height: 700 }, { width: 500, height: 1000 }]) {
    const fit = fitCanvasBounds(cards, canvas)!;
    const scale = canvas.width / fit.width;
    expect(fit.width / fit.height).toBeCloseTo(canvas.width / canvas.height);
    for (const card of cards) {
      expect((card.x + fit.offsetX) * scale).toBeGreaterThanOrEqual(39.99);
      expect((card.y + fit.offsetY) * scale).toBeGreaterThanOrEqual(39.99);
      expect((card.x + card.width + fit.offsetX) * scale).toBeLessThanOrEqual(canvas.width - 39.99);
      expect((card.y + card.height + fit.offsetY) * scale).toBeLessThanOrEqual(canvas.height - 39.99);
    }
  }
  expect(fitCanvasBounds([], { width: 1000, height: 700 })).toBeNull();
});

test("fit canvas recenters the actual dragged nodes rather than resetting zoom alone", () => {
  const { container } = render(<GoalNetworkPresentation model={model} loops={[]} />);
  const node = screen.getByRole("button", { name: "目标：目标业务" });
  for (let i = 0; i < 40; i++) fireEvent.keyDown(node, { key: "ArrowLeft" });
  const graph = container.querySelector(".network-canvas svg > g")!;
  const before = graph.getAttribute("transform");
  fireEvent.click(screen.getByRole("button", { name: "适应画布" }));
  expect(graph.getAttribute("transform")).not.toBe(before);
  expect(graph.getAttribute("transform")).not.toBe("translate(0,0) scale(1)");
});

test("toolbar panel controls hide collapsed rails and show the open state", () => {
  const { container } = render(<GoalNetworkPresentation model={model} loops={[]} />);
  const navigation = screen.getByRole("button", { name: "展开经营网络导航" });
  expect(navigation.closest(".network-controls")).not.toBeNull();
  expect(container.querySelector(".onto-side-left")).not.toBeVisible();
  fireEvent.click(navigation);
  expect(screen.getByRole("button", { name: "收起经营网络导航" })).toHaveAttribute("aria-expanded", "true");
  expect(container.querySelector(".onto-side-left")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "收起经营网络导航" }));
  expect(container.querySelector(".onto-side-left")).not.toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "收起网络详情" }));
  expect(container.querySelector(".onto-side-right")).not.toBeVisible();
  expect(screen.getByRole("button", { name: "展开网络详情" }).closest(".network-controls")).not.toBeNull();
});

test("large company goals progressively reveal real edges and retain the complete network", () => {
  const root = { ...nodes[0], id: "company-root", name: "实现公司长期可持续经营与利润最大化" };
  const members = Array.from({ length: 63 }, (_, i) => ({ ...nodes[0], id: `company-${i}`, name: `经营目标${i}`, parent_candidate_id: root.id }));
  const relations = members.map((member, i) => edge("advances", member.id, i % 21 === 0 ? root.id : members[i - 1].id));
  const fixture = { ...model, submission_mode: "patch" as const, candidates: [root, ...members], relations };
  const original = JSON.stringify(fixture);
  const { container } = render(<GoalNetworkPresentation model={fixture} loops={[]} />);
  expect(screen.getByRole("button", { name: "核心概览" })).toHaveAttribute("aria-pressed", "true");
  expect(container.querySelectorAll(".network-node")).toHaveLength(4);
  expect(container.querySelectorAll(".network-edge")).toHaveLength(3);
  fireEvent.click(screen.getByRole("button", { name: "经营目标0展开关联" }));
  expect(container.querySelectorAll(".network-node")).toHaveLength(5);
  expect(container.querySelectorAll(".network-edge")).toHaveLength(4);
  fireEvent.click(screen.getByRole("button", { name: "完整网络" }));
  expect(container.querySelectorAll(".network-node")).toHaveLength(64);
  expect(container.querySelectorAll(".network-edge")).toHaveLength(63);
  fireEvent.click(screen.getByRole("button", { name: "核心概览" }));
  expect(container.querySelectorAll(".network-node")).toHaveLength(4);
  expect(JSON.stringify(fixture)).toBe(original);
});

test("modified wheel zooms only the canvas and respects zoom limits", () => {
  const { container } = render(<GoalNetworkPresentation model={model} loops={[]} />);
  const canvas = container.querySelector(".network-canvas")!;
  const percentage = () => container.querySelector(".network-zoom span")!.textContent;
  fireEvent.wheel(canvas, { deltaY: -100 });
  expect(percentage()).toBe("100%");
  const wheel = new WheelEvent("wheel", { deltaY: -100, ctrlKey: true, cancelable: true });
  act(() => { canvas.dispatchEvent(wheel); });
  expect(wheel.defaultPrevented).toBe(true);
  expect(percentage()).toBe("122%");
  for (let i = 0; i < 20; i++) fireEvent.wheel(canvas, { deltaY: -150, metaKey: true });
  expect(percentage()).toBe("1000%");
  for (let i = 0; i < 30; i++) fireEvent.wheel(canvas, { deltaY: 150, ctrlKey: true });
  expect(percentage()).toBe("40%");
});

test.each(["提升 FULLY 项目盈利能力", "提升增长资产与市场洞察能力", "提升新品上市成功率"])("directory goal %s opens its complete scoped network", (goalName) => {
  const aggregate = { ...nodes[0], id: "aggregate", name: "提升各品牌项目盈利能力" };
  const project = { ...nodes[0], id: "fully", name: goalName };
  const sales = { ...nodes[0], id: "sales", name: "FULLY销售", parent_candidate_id: "fully" };
  const supply = { ...nodes[1], id: "supply", name: "FULLY采购", parent_candidate_id: "fully" };
  const fixture: GoalModelView = { ...model, submission_mode: "patch", candidates: [aggregate, project, sales, supply],
    relations: [edge("advances", "fully", "aggregate"), edge("drives", "sales", "fully"), edge("enables", "supply", "sales")] };
  const { container } = render(<GoalNetworkPresentation model={fixture} loops={[]} />);
  fireEvent.click(screen.getByRole("button", { name: "展开经营网络导航" }));
  fireEvent.click(screen.getByRole("button", { name: goalName }));
  expect(screen.getByRole("combobox", { name: "当前业务 Goal" })).toHaveValue("fully");
  expect(screen.getByRole("combobox", { name: "网络展示范围" })).toHaveValue("business");
  expect(screen.getByRole("checkbox", { name: "显示支撑关系" })).toBeChecked();
  expect(container.querySelectorAll(".network-node")).toHaveLength(4);
  expect(container.querySelectorAll(".network-edge")).toHaveLength(3);
});

test("support switch reveals endpoints and restores automatic types when disabled", () => {
  const supportModel = { ...model, candidates: [nodes[0], nodes[4]], relations: [edge("measures", "n4", "n0")] };
  const before = JSON.stringify(supportModel);
  const { container } = render(<GoalNetworkPresentation model={supportModel} loops={[]} />);
  expect(screen.getByRole("status")).toHaveTextContent("被当前筛选隐藏");
  const checkbox = screen.getByRole("checkbox", { name: "显示支撑关系" });
  fireEvent.click(checkbox);
  expect(container.querySelectorAll(".network-node")).toHaveLength(2);
  expect(container.querySelectorAll(".network-edge")).toHaveLength(1);
  expect(screen.getByRole("button", { name: "指标" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(checkbox);
  expect(screen.getByRole("button", { name: "指标" })).toHaveAttribute("aria-pressed", "false");
  expect(screen.getByRole("status")).toHaveTextContent("被当前筛选隐藏");
  expect(JSON.stringify(supportModel)).toBe(before);
});

test("empty state recovers filtered causal endpoints", () => {
  const { container } = render(<GoalNetworkPresentation model={{ ...model, candidates: [nodes[0], nodes[2]], relations: [edge("advances")] }} loops={[]} />);
  fireEvent.click(screen.getByRole("button", { name: "风险" }));
  expect(screen.getByRole("status")).toHaveTextContent("被当前筛选隐藏");
  fireEvent.click(screen.getByRole("button", { name: "显示当前范围的关联关系" }));
  expect(container.querySelectorAll(".network-node")).toHaveLength(2);
  expect(container.querySelectorAll(".network-edge")).toHaveLength(1);
});

test("missing semantic data offers hierarchy without fabricating a network", () => {
  const onShowHierarchy = jest.fn();
  const { container } = render(<GoalNetworkPresentation model={{ ...model, candidates: [nodes[0]], relations: [] }} loops={[]} onShowHierarchy={onShowHierarchy} />);
  expect(screen.getByRole("status")).toHaveTextContent("尚未建立经营影响关系");
  fireEvent.click(screen.getByRole("button", { name: "查看目标层级" }));
  expect(onShowHierarchy).toHaveBeenCalledTimes(1);
  expect(container.querySelectorAll(".network-node, .network-edge")).toHaveLength(0);
});

test("manually enabled supporting types survive support switch off", () => {
  render(<GoalNetworkPresentation model={model} loops={[]} />);
  fireEvent.click(screen.getByRole("button", { name: "指标" }));
  const checkbox = screen.getByRole("checkbox", { name: "显示支撑关系" });
  fireEvent.click(checkbox);
  fireEvent.click(checkbox);
  expect(screen.getByRole("button", { name: "指标" })).toHaveAttribute("aria-pressed", "true");
});

test("all six business node types and nine Chinese relation labels", () => {
  expect(Object.keys(NODE_LABELS)).toHaveLength(6);
  expect(Object.keys(RELATION_LABELS)).toHaveLength(9);
  expect(businessName({ name: "C2 全渠道控价体系", description: "" })).toBe("全渠道控价体系");
  expect(businessName({ name: "C:陈华俊:UN项目利润分", description: "" })).toBe("C:陈华俊:UN项目利润分");
});

test("company project heading opens its business scope without changing data", () => {
  const project = { ...nodes[0], name: "提升 UN 项目盈利能力" };
  const fixture = { ...model, candidates: [project, nodes[2]], relations: [edge("blocks", "n2", "n0")] };
  const before = JSON.stringify(fixture);
  const { container } = render(<GoalNetworkPresentation model={fixture} loops={[]} />);
  fireEvent.click(screen.getByRole("button", { name: "展开经营网络导航" }));
  fireEvent.change(screen.getByRole("combobox", { name: "网络展示范围" }), { target: { value: "global" } });
  const heading = container.querySelector(".network-cluster text[role=button]")!;
  expect(heading).toHaveTextContent("提升 UN 项目盈利能力");
  fireEvent.click(heading);
  expect(screen.getByRole("combobox", { name: "网络展示范围" })).toHaveValue("business");
  expect(screen.getByRole("combobox", { name: "当前业务 Goal" })).toHaveValue("n0");
  expect(JSON.stringify(fixture)).toBe(before);
});

test("company defaults to original card scale; fit all is an explicit action", () => {
  const project = { ...nodes[0], name: "提升 UN 项目盈利能力" };
  const children = Array.from({ length: 30 }, (_, i) => ({ ...nodes[0], id: `child-${i}`, name: `经营目标 ${i}`, parent_candidate_id: project.id }));
  const fixture = { ...model, candidates: [project, ...children], relations: children.map(n => ({ ...edge("advances", n.id, project.id), id: `edge-${n.id}` })) };
  const { container } = render(<GoalNetworkPresentation model={fixture} loops={[]} />);
  fireEvent.click(screen.getByRole("button", { name: "展开经营网络导航" }));
  fireEvent.change(screen.getByRole("combobox", { name: "网络展示范围" }), { target: { value: "global" } });
  expect(container.querySelector(".network-canvas")).toHaveAttribute("data-lod", "medium");
  expect(container.querySelector(".network-node strong")).toHaveStyle({ fontSize: "13px" });
  expect(container.querySelector(".network-node [data-node-type]")).toHaveStyle({ fontSize: "9px" });
  fireEvent.click(screen.getByRole("button", { name: "适应画布" }));
  expect(container.querySelector(".network-canvas")).toHaveAttribute("data-lod", "far");
  fireEvent.click(screen.getByRole("group", { name: "公司分区定位" }).querySelector("button")!);
  expect(container.querySelector(".network-canvas")).toHaveAttribute("data-lod", "medium");
});
test("snapshot filtering and display leave source payload unchanged", () => {
  const before = JSON.stringify(model);
  expect(currentNetwork(model).nodes).toHaveLength(6);
  layoutNetwork(nodes);
  expect(JSON.stringify(model)).toBe(before);
  expect(currentNetwork({ ...model, candidates: [...nodes, { ...nodes[0], id: "historic", status: "legacy_confirmed" }] }).nodes).toHaveLength(6);
});
test("semantic lanes never overlap as groups grow", () => {
  const positions = layoutNetwork(NETWORK_TYPES.flatMap(type => Array.from({ length: 13 }, (_, i) => ({ ...nodes[0], id: `${type}-${i}`, node_type: type }))));
  expect(new Set(positions.map(p => `${p.x},${p.y}`)).size).toBe(78);
});
test("goal hierarchy excludes non-goal business nodes", () => {
  expect(buildDerivedGoalTree(model, "zh").roots).toHaveLength(1);
});
test("default canvas shows goals, drivers and risks, others can be added", () => {
  const { container } = render(<GoalNetworkPresentation model={model} loops={[]} />);
  expect(container.querySelectorAll(".network-node")).toHaveLength(3);
  fireEvent.click(screen.getByRole("button", { name: "能力" }));
  expect(container.querySelectorAll(".network-node")).toHaveLength(3);
  fireEvent.click(screen.getByRole("checkbox", { name: "显示支撑关系" }));
  expect(container.querySelectorAll(".network-node")).toHaveLength(4);
  expect(screen.getByRole("button", { name: "能力：能力业务" })).toBeInTheDocument();
});
test("causal edges are solid and other relationships are structural", () => {
  const { container } = render(<GoalNetworkPresentation model={model} loops={[]} />);
  expect(container.querySelectorAll(".network-edge.is-causal")).toHaveLength(4);
  expect(container.querySelectorAll(".network-edge.is-structural")).toHaveLength(0);
  fireEvent.click(screen.getByRole("checkbox", { name: "显示支撑关系" }));
  expect(container.querySelectorAll(".network-edge.is-structural")).toHaveLength(5);
});
test("loop highlights only exact server edges and nodes", () => {
  const { container } = render(<GoalNetworkPresentation model={model} loops={[loop]} />);
  fireEvent.click(screen.getByRole("tab", { name: "反馈回路（1）" }));
  fireEvent.click(screen.getAllByRole("button", { name: /Loop 01/ })[0]);
  fireEvent.click(screen.getByRole("checkbox", { name: "显示支撑关系" }));
  expect(container.querySelectorAll('.network-edge[data-loop-highlighted="true"]')).toHaveLength(1);
  expect(container.querySelectorAll(".network-node.is-loop")).toHaveLength(2);
  expect(container.querySelector('.network-edge[data-relationship="serves"]')).toHaveAttribute("opacity", "0.08");
  expect(screen.getAllByText("平衡回路").length).toBeGreaterThan(0);
});
test("a project subgoal retains the full project context when opened from navigation", () => {
  const project = { ...nodes[0], id: "project", name: "提升 FULLY 项目盈利能力" };
  const child = { ...nodes[0], id: "child", name: "FULLY · 渠道回款与账期履约水平", parent_candidate_id: "project" };
  const other = { ...nodes[2], id: "risk", parent_candidate_id: "project" };
  const { container } = render(<GoalNetworkPresentation model={{ ...model, submission_mode: "patch", candidates: [project, child, other], relations: [edge("advances", "child", "project"), edge("blocks", "risk", "project")] }} loops={[]} />);
  fireEvent.click(screen.getByRole("button", { name: "展开经营网络导航" }));
  fireEvent.click(screen.getByRole("button", { name: child.name }));
  expect(screen.getByRole("combobox", { name: "当前业务 Goal" })).toHaveValue("project");
  expect(container.querySelectorAll(".network-node")).toHaveLength(3);
});

test("loop tab shares the right panel and excludes unrelated scopes", () => {
  const unrelated = { ...loop, loop_id: "other-project", nodes: ["other-a", "other-b"] };
  const { container } = render(<GoalNetworkPresentation model={model} loops={[loop, unrelated]} />);
  expect(container.querySelector(".network-main .network-loops")).toBeNull();
  expect(screen.getByRole("tab", { name: "节点详情" })).toHaveAttribute("aria-selected", "true");
  expect(container.querySelector(".network-loops")).toBeNull();
  fireEvent.click(screen.getByRole("tab", { name: "反馈回路（1）" }));
  const panel = container.querySelector(".network-loops")!;
  expect(container.querySelector("#network-details-panel")).toBeNull();
  expect(panel.querySelectorAll(".network-loop-card")).toHaveLength(1);
});

test("frontend does not invent loops even when relations form a cycle", () => {
  render(<GoalNetworkPresentation model={{ ...model, relations: [edge("advances"), edge("blocks", "n2", "n0")] }} loops={[]} loopView />);
  fireEvent.click(screen.getByRole("tab", { name: "反馈回路（0）" }));
  expect(screen.getAllByText("当前范围没有反馈回路").length).toBeGreaterThan(0);
  expect(screen.queryByText(/Loop 01/)).not.toBeInTheDocument();
});
test("loop filters preserve numbering, conditions and drawer selection", () => {
  const second = { ...loop, loop_id: "second", loop_type: "Reinforcing" as const, conditions: ["原始业务条件"], status: "CONDITIONAL" as const };
  const before = JSON.stringify([loop, second]);
  const { container } = render(<GoalNetworkPresentation model={model} loops={[loop, second]} />);
  fireEvent.click(screen.getByRole("tab", { name: "反馈回路（2）" }));
  fireEvent.change(screen.getByRole("combobox", { name: "反馈回路类型" }), { target: { value: "Reinforcing" } });
  expect(screen.queryByText("Loop 01")).not.toBeInTheDocument();
  expect(screen.getByText("Loop 02")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox", { name: "搜索反馈回路" }), { target: { value: "Loop 02" } });
  fireEvent.click(screen.getByRole("button", { name: "展开全部" }));
  expect(screen.getByText("条件：原始业务条件")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "收起 Loop 02" })).toHaveAttribute("aria-expanded", "true");
  const graph = container.querySelector(".network-canvas svg > g")!;
  const originalTransform = graph.getAttribute("transform");
  fireEvent.click(screen.getByRole("button", { name: "Loop 02 增强回路" }));
  expect(graph.getAttribute("transform")).not.toBe(originalTransform);
  expect(screen.getByRole("button", { name: "Loop 02 增强回路" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "收起网络详情" }));
  expect(container.querySelector(".onto-side-right")).toHaveClass("is-collapsed");
  fireEvent.click(screen.getByRole("button", { name: "展开网络详情" }));
  expect(screen.getByRole("tab", { name: "反馈回路（2）" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("button", { name: "Loop 02 增强回路" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("条件：原始业务条件")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "收起 Loop 02" }));
  expect(screen.queryByText("条件：原始业务条件")).not.toBeInTheDocument();
  expect(JSON.stringify([loop, second])).toBe(before);
});

test("canvas viewport follows drawer width changes through its existing resize observer", () => {
  const descriptor = Object.getOwnPropertyDescriptor(window, "ResizeObserver");
  const observers: Array<{ callback: ResizeObserverCallback; target?: Element }> = [];
  Object.defineProperty(window, "ResizeObserver", { configurable: true, value: class {
    entry: { callback: ResizeObserverCallback; target?: Element };
    constructor(callback: ResizeObserverCallback) { this.entry = { callback }; observers.push(this.entry); }
    observe(target: Element) { this.entry.target = target; }
    disconnect() {}
  } });
  try {
    const { container } = render(<GoalNetworkPresentation model={model} loops={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "展开经营网络导航" }));
    fireEvent.change(screen.getByRole("combobox", { name: "网络展示范围" }), { target: { value: "global" } });
    const canvasObserver = observers.find(observer => observer.target?.classList.contains("network-canvas"))!;
    const resize = (width: number) => act(() => canvasObserver.callback([{ contentRect: { width, height: 700 } } as ResizeObserverEntry], {} as ResizeObserver));
    resize(1000);
    const svg = container.querySelector(".network-canvas svg")!;
    expect(svg).toHaveAttribute("viewBox", "0 0 1000 700");
    fireEvent.click(screen.getByRole("button", { name: "收起网络详情" }));
    resize(1300);
    expect(svg).toHaveAttribute("viewBox", "0 0 1300 700");
    fireEvent.click(screen.getByRole("button", { name: "展开网络详情" }));
    resize(1000);
    expect(svg).toHaveAttribute("viewBox", "0 0 1000 700");
  } finally {
    if (descriptor) Object.defineProperty(window, "ResizeObserver", descriptor); else Reflect.deleteProperty(window, "ResizeObserver");
  }
});

test("current run includes existing canonical endpoints and keeps the full snapshot accessible", () => {
  const snapshot = { ...model, run_id: "new", relations: [{ ...edge("advances"), run_id: "new" }, { ...edge("serves", "n1", "n0"), run_id: "old" }] };
  expect(currentNetwork(snapshot).nodes.map(n => n.id)).toEqual(["n0", "n2"]);
  expect(currentNetwork(snapshot).relations).toHaveLength(1);
  expect(currentNetwork(snapshot, false).nodes).toHaveLength(6);
});
test("restores the original SVG collapse chevron", () => {
  const oldWidth = window.innerWidth;
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 1440 });
  const { container } = render(<GoalNetworkPresentation model={model} loops={[]} />);
  expect(container.querySelector("summary .onto-file-chevron path")).toHaveAttribute("d", "M3.2 1.6L6.8 5L3.2 8.4");
  Object.defineProperty(window, "innerWidth", { configurable: true, value: oldWidth });
});
test("moving nodes updates connecting edges without changing the model", () => {
  const before = JSON.stringify(model);
  const { container } = render(<GoalNetworkPresentation model={model} loops={[]} />);
  const node = screen.getByRole("button", { name: "目标：目标业务" });
  const card = node.closest("foreignObject")!;
  const x = Number(card.getAttribute("x"));
  const path = container.querySelector('.network-edge[data-relationship="advances"] path')!;
  const originalPath = path.getAttribute("d");
  fireEvent.keyDown(node, { key: "ArrowRight" });
  expect(Number(card.getAttribute("x"))).toBe(x + 20);
  expect(path.getAttribute("d")).not.toBe(originalPath);
  fireEvent.click(node);
  expect(screen.getByText("节点详情")).toBeInTheDocument();
  expect(JSON.stringify(model)).toBe(before);
});
test("pointer dragging moves only the node and avoids opening details", () => {
  const pointDescriptor = Object.getOwnPropertyDescriptor(window, "DOMPoint");
  const eventDescriptor = Object.getOwnPropertyDescriptor(window, "PointerEvent");
  const matrixDescriptor = Object.getOwnPropertyDescriptor(SVGElement.prototype, "getScreenCTM");
  Object.defineProperty(window, "PointerEvent", { configurable: true, value: class extends MouseEvent { pointerId = 1; } });
  Object.defineProperty(window, "DOMPoint", { configurable: true, value: class { constructor(public x: number, public y: number) {} matrixTransform() { return this; } } });
  Object.defineProperty(SVGElement.prototype, "getScreenCTM", { configurable: true, value: () => ({ inverse: () => ({}) }) });
  try {
    render(<GoalNetworkPresentation model={model} loops={[]} />);
    const node = screen.getByRole("button", { name: "目标：目标业务" });
    const card = node.closest("foreignObject")!;
    const x = Number(card.getAttribute("x")), y = Number(card.getAttribute("y"));
    fireEvent.pointerDown(node, { button: 0, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(node, { clientX: 160, clientY: 140 });
    fireEvent.pointerUp(node);
    fireEvent.click(node);
    expect(Number(card.getAttribute("x"))).toBe(x + 60);
    expect(Number(card.getAttribute("y"))).toBe(y + 40);
    expect(screen.getByRole("heading", { name: "经营网络" })).toBeInTheDocument();
  } finally {
    if (pointDescriptor) Object.defineProperty(window, "DOMPoint", pointDescriptor); else Reflect.deleteProperty(window, "DOMPoint");
    if (eventDescriptor) Object.defineProperty(window, "PointerEvent", eventDescriptor); else Reflect.deleteProperty(window, "PointerEvent");
    if (matrixDescriptor) Object.defineProperty(SVGElement.prototype, "getScreenCTM", matrixDescriptor); else Reflect.deleteProperty(SVGElement.prototype, "getScreenCTM");
  }
});
test("click enters one-hop Focus and allows two hops, all and exit", () => {
  render(<GoalNetworkPresentation model={model} loops={[]} />);
  fireEvent.click(screen.getByRole("button", { name: "目标：目标业务" }));
  expect(screen.getByRole("button", { name: "1跳" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "2跳" }));
  expect(screen.getByRole("button", { name: "2跳" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "全部" }));
  expect(screen.getByRole("button", { name: "全部" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "退出 Focus" }));
  expect(screen.queryByRole("button", { name: "1跳" })).not.toBeInTheDocument();
});
test("degree-zero nodes are shown only in the right panel until inspected", () => {
  const oldWidth = window.innerWidth;
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 1440 });
  const isolated = { ...nodes[0], id: "lonely", name: "孤立节点" };
  const { container } = render(<GoalNetworkPresentation model={{ ...model, candidates: [...nodes, isolated] }} loops={[]} />);
  fireEvent.change(screen.getByRole("combobox", { name: "网络展示范围" }), { target: { value: "global" } });
  expect(screen.getByRole("heading", { name: /未参与当前网络/ })).toHaveTextContent("未参与当前网络（1）");
  expect(screen.queryByRole("button", { name: "目标：孤立节点" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /目标 · 孤立节点/ }));
  expect(screen.getByRole("heading", { name: "孤立节点" })).toBeInTheDocument();
  expect(container.querySelectorAll(".network-node")).toHaveLength(3);
  Object.defineProperty(window, "innerWidth", { configurable: true, value: oldWidth });
});
test("zoom LOD removes descriptions at a distance and reveals detail when enlarged", () => {
  const { container } = render(<GoalNetworkPresentation model={model} loops={[]} />);
  for (let i = 0; i < 4; i++) fireEvent.click(screen.getByRole("button", { name: "缩小网络" }));
  expect(container.querySelector(".network-canvas")).toHaveAttribute("data-lod", "far");
  expect(container.querySelectorAll(".network-node [data-node-type]")).toHaveLength(container.querySelectorAll(".network-node").length);
  expect(container.querySelector(".network-node strong")).toHaveAttribute("title");
  expect(container.querySelector(".network-node-description")).toBeNull();
  for (let i = 0; i < 14; i++) fireEvent.click(screen.getByRole("button", { name: "放大网络" }));
  expect(container.querySelector(".network-canvas")).toHaveAttribute("data-lod", "near");
  expect(container.querySelector(".network-node-description")).not.toBeNull();
});
test("support footer stays inside the measured card, outside its main button", () => {
  render(<GoalNetworkPresentation model={model} loops={[]} />);
  const footerButton = screen.getByRole("button", { name: "目标业务展开附属能力" });
  expect(footerButton.closest(".network-node-card")).not.toBeNull();
  expect(footerButton.closest(".network-node")).toBeNull();
});
test("content resizing updates SVG dimensions and connecting edges on growth and shrink", () => {
  const observerDescriptor = Object.getOwnPropertyDescriptor(window, "ResizeObserver");
  const heightDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetHeight");
  let height = 128;
  const callbacks: (() => void)[] = [];
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, get() { return (this as HTMLElement).classList.contains("network-node-card") ? height : 0; } });
  Object.defineProperty(window, "ResizeObserver", { configurable: true, value: class {
    constructor(callback: ResizeObserverCallback) { callbacks.push(() => callback([], this as unknown as ResizeObserver)); }
    observe() {} disconnect() {}
  } });
  try {
    const { container } = render(<GoalNetworkPresentation model={model} loops={[]} />);
    const card = screen.getByRole("button", { name: "目标：目标业务" }).closest("foreignObject")!;
    const edge = container.querySelector('.network-edge[data-relationship="advances"] path')!;
    expect(card).toHaveAttribute("height", "128");
    const initialPath = edge.getAttribute("d");
    height = 240;
    act(() => callbacks.forEach(callback => callback()));
    expect(card).toHaveAttribute("height", "240");
    expect(edge.getAttribute("d")).not.toBe(initialPath);
    height = 100;
    act(() => callbacks.forEach(callback => callback()));
    expect(card).toHaveAttribute("height", "100");
  } finally {
    if (observerDescriptor) Object.defineProperty(window, "ResizeObserver", observerDescriptor); else Reflect.deleteProperty(window, "ResizeObserver");
    if (heightDescriptor) Object.defineProperty(HTMLElement.prototype, "offsetHeight", heightDescriptor);
  }
});
