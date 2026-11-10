"use client";

import { createPortal } from "react-dom";
import { useRef, useState } from "react";

export type Tip = {
  meaning: string;
  formula?: string;
  example?: string;
};

/**
 * Hover-to-decode metric. The label is dotted-underlined; hovering (or
 * keyboard-focusing) it opens a floating card with the plain-English meaning,
 * the formula and a real example. No click required.
 */
export default function MetricTip({
  label,
  tip,
  children,
  className = "",
  side = "auto",
}: {
  label: string;
  tip: Tip;
  children?: React.ReactNode;
  className?: string;
  side?: "auto" | "top" | "bottom";
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number; place: "top" | "bottom" } | null>(null);

  const show = () => {
    const el = ref.current;
    if (!el || typeof window === "undefined") return;
    const r = el.getBoundingClientRect();
    const place = side === "auto" ? (r.top > 240 ? "top" : "bottom") : side;
    setPos({ x: r.left + r.width / 2, y: place === "top" ? r.top : r.bottom, place });
  };
  const hide = () => setPos(null);

  const left = pos && typeof window !== "undefined"
    ? Math.min(Math.max(12, pos.x - 155), Math.max(12, window.innerWidth - 322))
    : 0;

  return (
    <>
      <span
        ref={ref}
        className={`metric-tip ${className}`}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        tabIndex={0}
        aria-label={`${label}: ${tip.meaning}`}
      >
        {children ?? label}
      </span>
      {pos && typeof document !== "undefined" &&
        createPortal(
          <div
            role="tooltip"
            className="tip-card fixed z-[200] w-[min(310px,calc(100vw-24px))] p-3.5 text-left"
            style={{
              left,
              top: pos.place === "top" ? pos.y - 10 : pos.y + 10,
              transform: pos.place === "top" ? "translateY(-100%)" : undefined,
            }}
            onMouseEnter={() => setPos(pos)}
            onMouseLeave={hide}
          >
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-[11px] font-bold uppercase tracking-[0.14em] accent">
                {label}
              </span>
              <span className="h-px flex-1" style={{ background: "var(--line)" }} />
            </div>
            <p className="text-[12.5px] leading-relaxed" style={{ color: "var(--ink)" }}>
              {tip.meaning}
            </p>
            {tip.formula && (
              <div className="mt-2 rounded-md px-2.5 py-1.5 knum text-[11.5px]"
                   style={{ background: "var(--surface-2)", border: "1px solid var(--line)", color: "var(--accent)" }}>
                {tip.formula}
              </div>
            )}
            {tip.example && (
              <p className="mt-2 text-[11.5px] leading-relaxed muted">
                <span className="font-semibold" style={{ color: "var(--ink)" }}>Example · </span>
                {tip.example}
              </p>
            )}
          </div>,
          document.body,
        )}
    </>
  );
}
