import { fireEvent, render } from "@testing-library/react";
import OntologyCanvas from "./OntologyCanvas";

beforeAll(() => {
  global.ResizeObserver = class {
    observe() {}
    disconnect() {}
    unobserve() {}
  };
});

it("pans from a right drag even when the canvas has no scrollable overflow", () => {
  const pointer = (target: Element | Window, type: string, clientX: number, clientY: number) => {
    const event = new MouseEvent(type, { bubbles: true, button: 2, clientX, clientY });
    Object.defineProperty(event, "pointerId", { value: 7 });
    fireEvent(target, event);
  };
  const { container } = render(
    <OntologyCanvas
      focusId="goal"
      entities={[{ id: "goal", name: "Goal", type: "Goal", kind: "Goal" }]}
      edges={[]}
      selectedId={null}
      viewMode="relation"
      hopDepth={1}
      relatedOnly={false}
      hiddenRels={new Set()}
      hoverId={null}
      language="zh"
      onSelect={jest.fn()}
      onSetFocus={jest.fn()}
      onExpand={jest.fn()}
      onCanvasClick={jest.fn()}
      onHover={jest.fn()}
    />,
  );
  const canvas = container.querySelector(".onto-canvas")!;
  const card = container.querySelector(".onto-entity-card")!;

  pointer(card, "pointerdown", 100, 100);
  pointer(window, "pointermove", 150, 125);

  expect(canvas.querySelector<HTMLElement>("div[style*='translate(50px, 25px)']")).not.toBeNull();
  pointer(window, "pointerup", 150, 125);
});
