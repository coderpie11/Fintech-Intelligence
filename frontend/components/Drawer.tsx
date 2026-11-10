"use client";

import { useEffect } from "react";

/** Right-hand slide-over used by the peer drawers. Renders through a fixed
    overlay so it never disturbs the page layout behind it. */
export default function Drawer({
  open,
  onClose,
  title,
  eyebrow,
  children,
  width = 560,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  eyebrow?: string;
  children: React.ReactNode;
  width?: number;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[120] flex justify-end" role="dialog" aria-modal="true"
         aria-label={title}>
      <div className="absolute inset-0 bg-black/55 backdrop-blur-[2px]" onClick={onClose} />
      <aside
        className="relative h-full overflow-y-auto"
        style={{
          width: `min(${width}px, 100vw)`,
          background: "var(--surface)",
          borderLeft: "1px solid var(--line)",
          boxShadow: "-24px 0 60px -24px rgba(2,6,23,.8)",
          animation: "slideIn .22s ease-out both",
        }}
      >
        <div className="sticky top-0 z-10 flex items-start justify-between gap-3 px-4 sm:px-5 py-4"
             style={{ background: "var(--surface)", borderBottom: "1px solid var(--line)" }}>
          <div>
            {eyebrow && (
              <div className="muted text-[10px] font-bold uppercase tracking-[0.16em] mb-1">
                {eyebrow}
              </div>
            )}
            <h2 className="text-[17px] font-extrabold tracking-tight">{title}</h2>
          </div>
          <button onClick={onClose} aria-label="Close drawer"
                  className="btn-secondary !px-2.5 !py-1.5 !text-[13px]">✕</button>
        </div>
        <div className="p-4 sm:p-5">{children}</div>
      </aside>
      <style>{`@keyframes slideIn { from { transform: translateX(28px); opacity: .4 } to { transform: translateX(0); opacity: 1 } }`}</style>
    </div>
  );
}
