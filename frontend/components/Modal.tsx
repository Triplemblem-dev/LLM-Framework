"use client";

import { useEffect, useRef } from "react";

interface ModalProps {
  open: boolean;
  title: string;
  subtitle: string;
  confirmLabel?: string;
  confirmDanger?: boolean;
  confirmDisabled?: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  children: React.ReactNode;
}

export function Modal({
  open,
  title,
  subtitle,
  confirmLabel = "Create",
  confirmDanger = false,
  confirmDisabled = false,
  onClose,
  onConfirm,
  children,
}: ModalProps) {
  const backdropRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <div
      className={`backdrop${open ? " open" : ""}`}
      ref={backdropRef}
      onMouseDown={(e) => {
        if (e.target === backdropRef.current) onClose();
      }}
    >
      {open && (
        <div className="modal">
          <h2>{title}</h2>
          <div className="sub">{subtitle}</div>
          {children}
          <div className="modal-actions">
            <button className="btn-text" onClick={onClose} type="button">
              Cancel
            </button>
            <button
              className={`btn-primary${confirmDanger ? " danger" : ""}`}
              onClick={onConfirm}
              type="button"
              disabled={confirmDisabled}
            >
              {confirmLabel}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
