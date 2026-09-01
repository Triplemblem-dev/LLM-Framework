"use client";

import { useEffect, useState } from "react";
import { ToastItem } from "../lib/types";

export function Toasts({ toasts }: { toasts: ToastItem[] }) {
  return (
    <div className="toasts">
      {toasts.map((t) => (
        <Toast key={t.id} message={t.message} />
      ))}
    </div>
  );
}

function Toast({ message }: { message: string }) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setShow(true));
    return () => cancelAnimationFrame(id);
  }, []);
  return <div className={`toast${show ? " show" : ""}`}>{message}</div>;
}
