"use client";

import type { ReactNode } from "react";

export default function SideRail({
  side,
  open,
  onOpen,
  expandLabel,
  children,
}: {
  side: "left" | "right";
  open: boolean;
  onOpen: () => void;
  expandLabel: string;
  children: ReactNode;
}) {
  return (
    <div className={`onto-side-container onto-side-${side}${open ? "" : " is-collapsed"}`}>
      {open ? (
        children
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
