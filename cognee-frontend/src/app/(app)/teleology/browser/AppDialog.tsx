"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { Modal } from "@mantine/core";

export default function AppDialog({
  opened,
  title,
  description,
  confirmLabel,
  cancelLabel,
  danger = false,
  onCancel,
  onConfirm,
  children,
}: {
  opened: boolean;
  title: string;
  description?: string;
  confirmLabel: string;
  cancelLabel: string;
  danger?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  children?: ReactNode;
}) {
  const firstField = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!opened) return;
    const frame = window.requestAnimationFrame(() => {
      const field = firstField.current?.querySelector("input, select, textarea");
      if (field instanceof HTMLElement) field.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [opened]);

  return (
    <Modal.Root opened={opened} onClose={onCancel} size={440} centered trapFocus returnFocus closeOnEscape closeOnClickOutside>
      <Modal.Overlay style={{ background: "rgba(0,0,0,0.55)" }} />
      <Modal.Content aria-label={title} style={{ background: "transparent", boxShadow: "none", padding: 0 }}>
        <div className="onto-dialog">
          <Modal.Body style={{ padding: 0 }}>
            <h2>{title}</h2>
            {description ? <p>{description}</p> : null}
            <div ref={firstField}>{children}</div>
            <div className="onto-dialog-actions">
              <button type="button" className="onto-btn" onClick={onCancel}>{cancelLabel}</button>
              <button type="button" className={`onto-btn${danger ? " onto-btn-danger" : " onto-btn-primary"}`} onClick={onConfirm}>{confirmLabel}</button>
            </div>
          </Modal.Body>
        </div>
      </Modal.Content>
    </Modal.Root>
  );
}
