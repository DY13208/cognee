import { fireEvent, render, screen } from "@testing-library/react";
import SideRail from "./SideRail";

it("resizes the left goal navigation and restores the saved width", () => {
  window.localStorage.clear();
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 1600 });
  const pointer = (target: Element, type: string, x: number) => {
    const event = new MouseEvent(type, { bubbles: true, button: 0, clientX: x });
    Object.defineProperty(event, "pointerId", { value: 4 });
    fireEvent(target, event);
  };
  const view = render(<SideRail side="left" open onOpen={jest.fn()} expandLabel="Expand" resizeLabel="Resize goals"><div>Goals</div></SideRail>);
  const handle = screen.getByRole("separator", { name: "Resize goals" });
  const rail = handle.parentElement!;

  pointer(handle, "pointerdown", 300);
  pointer(handle, "pointermove", 420);
  expect(rail).toHaveStyle({ width: "384px" });
  pointer(handle, "pointerup", 420);
  expect(window.localStorage.getItem("teleology.goalNavWidth")).toBe("384");

  view.rerender(<SideRail side="left" open={false} onOpen={jest.fn()} expandLabel="Expand"><div>Goals</div></SideRail>);
  fireEvent.click(screen.getByRole("button", { name: "Expand" }));
  view.rerender(<SideRail side="left" open onOpen={jest.fn()} expandLabel="Expand"><div>Goals</div></SideRail>);
  expect(screen.getByRole("separator").parentElement).toHaveStyle({ width: "384px" });

  view.unmount();
  render(<SideRail side="left" open onOpen={jest.fn()} expandLabel="Expand"><div>Goals</div></SideRail>);
  expect(screen.getByRole("separator").parentElement).toHaveStyle({ width: "384px" });
});
