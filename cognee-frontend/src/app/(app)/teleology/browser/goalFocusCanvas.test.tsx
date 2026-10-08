import { fireEvent, render, screen } from "@testing-library/react";
import OntologyCanvas from "./OntologyCanvas";
import NavPanel from "./NavPanel";

beforeEach(() => {
  global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver;
});

it("preserves an unconnected upper parent and all real semantic edges in context layout", () => {
  const entities = ["parent", "goal", "capability"].map(id => ({ id, name: id, type: "Goal", kind: "Goal" as const }));
  const { container } = render(<OntologyCanvas focusId="goal" entities={entities} edges={[{ id: "actual", sourceId: "capability", targetId: "goal", sourceName: "capability", targetName: "goal", sourceType: "Capability", targetType: "Goal", relationship: "enables" }]} positions={{ parent: { x: 300, y: 40 }, goal: { x: 300, y: 220 }, capability: { x: 20, y: 220 } }} selectedId="goal" viewMode="relation" hopDepth={2} relatedOnly={false} hiddenRels={new Set()} hoverId={null} language="zh" onSelect={() => {}} onSetFocus={() => {}} onExpand={() => {}} onCanvasClick={() => {}} onHover={() => {}} />);
  expect(container.querySelectorAll(".onto-entity-card")).toHaveLength(3);
  expect(screen.getByText("parent")).toBeVisible();
  expect(screen.getByText("支撑")).toBeVisible();
});

it("keeps the brand navigation group collapsed until explicitly selected", () => {
  const pick = jest.fn();
  const root = { id: "profit", name: "公司利润", type: "Goal", source: "derived_goal", description: "", child_count: 1 };
  const group = { ...root, id: "ui:brands:profit", name: "品牌项目（22）", child_count: 22 };
  const brand = { ...root, id: "brand", name: "DR.BANGGIWON", child_count: 0 };
  render(<NavPanel language="zh" roots={[root]} pages={{ profit: { items: [group], total: 1, loaded: true, loading: false }, [group.id]: { items: [brand], total: 1, loaded: true, loading: false } }} focusId="profit" pathIds={["profit"]} loading={false} onPick={pick} onExpand={() => {}} onSearch={async () => []} onClose={() => {}} />);
  expect(screen.queryByRole("button", { name: "DR.BANGGIWON" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "品牌项目（22）" }));
  expect(screen.getByRole("button", { name: "DR.BANGGIWON" })).toBeVisible();
  expect(pick).toHaveBeenCalledWith(group.id, group);
});
