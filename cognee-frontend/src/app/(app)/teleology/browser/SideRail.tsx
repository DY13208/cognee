"use client";

import { useCallback, useEffect, useRef, useState, type PointerEvent, type ReactNode } from "react";

const DEFAULT_LEFT_WIDTH = 264;
const MIN_LEFT_WIDTH = 240;
const MAX_LEFT_WIDTH = 720;
const LEFT_WIDTH_KEY = "teleology.goalNavWidth";

export default function SideRail({
  side,
  open,
  onOpen,
  expandLabel,
  resizeLabel,
  hideCollapsedRail = false,
  children,
}: {
  side: "left" | "right";
  open: boolean;
  onOpen: () => void;
  expandLabel: string;
  resizeLabel?: string;
  hideCollapsedRail?: boolean;
  children: ReactNode;
}) {
  const railRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ pointerId: number; startX: number; startWidth: number } | null>(null);
  const previousUserSelect = useRef("");
  const [width, setWidth] = useState(DEFAULT_LEFT_WIDTH);
  const [resizing, setResizing] = useState(false);

  const maxWidth = useCallback(() => {
    if (typeof window === "undefined") return MAX_LEFT_WIDTH;
    const body = railRef.current?.closest(".onto-body");
    const bodyWidth = body?.clientWidth || window.innerWidth;
    const rightWidth = body?.querySelector<HTMLElement>(".onto-side-right")?.clientWidth || 340;
    return Math.max(MIN_LEFT_WIDTH, Math.min(MAX_LEFT_WIDTH, bodyWidth - rightWidth - 320));
  }, []);
  const clampWidth = useCallback((value: number) => Math.max(MIN_LEFT_WIDTH, Math.min(maxWidth(), value)), [maxWidth]);

  useEffect(() => {
    if (side !== "left") return;
    const saved = Number(window.localStorage.getItem(LEFT_WIDTH_KEY));
    setWidth(clampWidth(Number.isFinite(saved) && saved >= MIN_LEFT_WIDTH ? saved : DEFAULT_LEFT_WIDTH));
    const onResize = () => setWidth((current) => clampWidth(current));
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      if (dragRef.current) document.body.style.userSelect = previousUserSelect.current;
    };
  }, [side, clampWidth]);

  function finishResize() {
    dragRef.current = null;
    setResizing(false);
    document.body.style.userSelect = previousUserSelect.current;
  }

  function startResize(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    event.preventDefault();
    dragRef.current = { pointerId: event.pointerId, startX: event.clientX, startWidth: width };
    previousUserSelect.current = document.body.style.userSelect;
    document.body.style.userSelect = "none";
    setResizing(true);
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function moveResize(event: PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || event.pointerId !== drag.pointerId) return;
    setWidth(clampWidth(drag.startWidth + event.clientX - drag.startX));
  }

  function endResize(event: PointerEvent<HTMLDivElement>) {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    const next = clampWidth(dragRef.current.startWidth + event.clientX - dragRef.current.startX);
    setWidth(next);
    window.localStorage.setItem(LEFT_WIDTH_KEY, String(next));
    finishResize();
  }

  return (
    <div ref={railRef} hidden={!open && hideCollapsedRail} className={`onto-side-container onto-side-${side}${open ? "" : " is-collapsed"}${resizing ? " is-resizing" : ""}`} style={!open && hideCollapsedRail ? { display: "none" } : side === "left" && open ? { width } : undefined}>
      {open ? (
        <>
          {children}
          {side === "left" && <div
            className="onto-side-resize-handle"
            role="separator"
            tabIndex={0}
            aria-label={resizeLabel || "Resize goal sidebar"}
            aria-orientation="vertical"
            aria-valuemin={MIN_LEFT_WIDTH}
            aria-valuemax={maxWidth()}
            aria-valuenow={width}
            onPointerDown={startResize}
            onPointerMove={moveResize}
            onPointerUp={endResize}
            onPointerCancel={finishResize}
            onLostPointerCapture={finishResize}
            onDoubleClick={() => { const next = clampWidth(DEFAULT_LEFT_WIDTH); setWidth(next); window.localStorage.setItem(LEFT_WIDTH_KEY, String(next)); }}
            onKeyDown={(event) => {
              if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
              event.preventDefault();
              const next = clampWidth(width + (event.key === "ArrowRight" ? 24 : -24));
              setWidth(next);
              window.localStorage.setItem(LEFT_WIDTH_KEY, String(next));
            }}
          />}
        </>
      ) : (
        <div className="onto-side-rail">
          <button type="button" className="onto-panel-reopen" onClick={onOpen} aria-label={expandLabel}>
            {side === "left" ? "›" : "‹"}
          </button>
        </div>
      )}
    </div>
  );
}
