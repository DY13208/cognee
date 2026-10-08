import { render, screen } from "@testing-library/react";
import EntityCard from "./EntityCard";
import { GoalNetworkPresentation } from "./GoalNetworkView";
import type { LaidOutNode } from "./types";
import type { GoalModelView } from "@/modules/teleology/teleologyApi";

test("hierarchy and network cards share surface, title and type badge styles", () => {
  const model = { candidates: [{ id: "goal", node_type: "goal", name: "经营目标", status: "confirmed", evidence: [] }, { id: "risk", node_type: "risk", name: "风险", status: "confirmed" }], relations: [{ id: "edge", source: "risk", target: "goal", relationship: "blocks", status: "confirmed" }], hierarchy: [] } as unknown as GoalModelView;
  const { container } = render(<><EntityCard node={{ id: "tree", name: "层级目标", type: "Goal", kind: "Goal", x: 0, y: 0 } as LaidOutNode} selected={false} isFocus={false} onSelect={() => {}} onFocus={() => {}} language="zh" relationshipCount={1} /><GoalNetworkPresentation model={model} loops={[]} /></>);
  const hierarchy = container.querySelector<HTMLElement>(".onto-entity-card")!;
  const network = screen.getByRole("button", { name: "目标：经营目标" }).closest<HTMLElement>(".onto-entity-card")!;
  expect(hierarchy).toHaveAttribute("data-component", "node-card");
  expect(network).toHaveAttribute("data-component", "node-card");
  expect(hierarchy.style.height).toBe("auto");
  expect(network.style.height).toBe("auto");
  for (const property of ["width", "background", "border", "borderRadius", "padding", "boxShadow", "fontFamily"] as const) expect(network.style[property]).toBe(hierarchy.style[property]);
  expect(network.querySelector("strong")!.getAttribute("style")).toBe(hierarchy.querySelector("strong")!.getAttribute("style"));
  expect(network.querySelector<HTMLElement>("[data-node-type]")!.style.borderRadius).toBe(hierarchy.querySelector<HTMLElement>('span[style*="border-radius: 999px"]')!.style.borderRadius);
});
test("network uses original cubic connection, subtle arrow and relation pill", () => {
  const model = { candidates: [{ id: "goal", name: "经营目标", node_type: "goal", status: "confirmed" }, { id: "risk", name: "风险", node_type: "risk", status: "confirmed" }], relations: [{ id: "edge", source: "risk", target: "goal", relationship: "blocks", status: "confirmed" }], hierarchy: [] } as unknown as GoalModelView;
  const { container } = render(<GoalNetworkPresentation model={model} loops={[]} />);
  const edge = container.querySelector(".network-edge path")!;
  expect(edge.getAttribute("d")).toContain(" C ");
  expect(edge.getAttribute("d")).not.toContain(" Q");
  expect(edge).toHaveStyle({ strokeWidth: 1.25 });
  expect(container.querySelector("#network-arrow")).toHaveAttribute("markerWidth", "6");
  expect(container.querySelector(".network-edge-label")).toHaveTextContent("阻碍");
});
