"use client";

import type { ReactNode } from "react";
import MetricTip, { type Tip } from "@/components/MetricTip";

/** Shared presentation primitives for the AI Quant Hub workspaces. */

export function Panel({
  title,
  sub,
  right,
  children,
  className = "",
}: {
  title?: string;
  sub?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card p-4 sm:p-5 ${className}`}>
      {(title || right) && (
        <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
          <div>
            {title && <h3 className="text-[14px] font-extrabold tracking-tight">{title}</h3>}
            {sub && <p className="muted text-[11.5px] mt-1 max-w-2xl leading-relaxed">{sub}</p>}
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function Metric({
  label,
  value,
  sub,
  tone = "neutral",
  tip,
  mono = true,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "neutral" | "up" | "down" | "warn" | "accent";
  tip?: Tip;
  mono?: boolean;
}) {
  const color =
    tone === "up" ? "text-up" :
    tone === "down" ? "text-down" :
    tone === "warn" ? "text-[var(--warn)]" :
    tone === "accent" ? "accent" : "";
  return (
    <div className="rounded-lg px-3 py-2.5" style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
      <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">
        {tip ? <MetricTip label={label} tip={tip}>{label}</MetricTip> : label}
      </div>
      <div className={`${mono ? "knum" : ""} text-[15px] font-bold mt-1 ${color}`}>{value}</div>
      {sub && <div className="muted text-[10.5px] mt-0.5 leading-snug">{sub}</div>}
    </div>
  );
}

export function Pill({
  children,
  tone = "neutral",
  title,
}: {
  children: ReactNode;
  tone?: "neutral" | "up" | "down" | "warn" | "accent";
  title?: string;
}) {
  const cls =
    tone === "up" ? "chip chip-live" :
    tone === "warn" ? "chip chip-warn" :
    tone === "accent" ? "chip chip-active" : "chip";
  const style =
    tone === "down"
      ? {
          color: "var(--down)",
          borderColor: "color-mix(in srgb, var(--down) 35%, var(--line))",
          background: "color-mix(in srgb, var(--down) 10%, transparent)",
        }
      : undefined;
  return <span className={`${cls} !text-[9.5px] !py-0.5`} style={style} title={title}>{children}</span>;
}

export function Bar({ value, tone = "accent" }: { value: number; tone?: "accent" | "up" | "down" | "warn" }) {
  const pct = Math.max(0, Math.min(100, value));
  const color =
    tone === "up" ? "var(--up)" :
    tone === "down" ? "var(--down)" :
    tone === "warn" ? "var(--warn)" : "var(--accent)";
  return (
    <div className="h-1.5 w-full rounded-full overflow-hidden" style={{ background: "var(--line)" }}>
      <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}

export function Loading({ label = "Loading the workspace…" }: { label?: string }) {
  return (
    <div className="card p-6 flex items-center gap-3" aria-busy="true">
      <span className="h-4 w-4 rounded-full border-2 border-t-transparent animate-spin"
            style={{ borderColor: "var(--accent)", borderTopColor: "transparent" }} />
      <span className="muted text-[12.5px]">{label}</span>
    </div>
  );
}

export function ErrLine({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="card p-4 flex flex-wrap items-center gap-3"
         style={{ borderColor: "color-mix(in srgb, var(--warn) 35%, var(--line))" }}>
      <span className="h-2 w-2 rounded-full bg-[var(--warn)] shrink-0" />
      <span className="text-[12.5px] flex-1">{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="btn-secondary !px-3 !py-1.5 !text-[11.5px]">Retry</button>
      )}
    </div>
  );
}

export function Note({ children }: { children: ReactNode }) {
  return <p className="muted text-[11px] leading-relaxed mt-2">{children}</p>;
}

export function num(n: number | null | undefined, dec = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-IN", { maximumFractionDigits: dec, minimumFractionDigits: 0 });
}

export function signed(n: number | null | undefined, dec = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${n > 0 ? "+" : ""}${num(n, dec)}`;
}
