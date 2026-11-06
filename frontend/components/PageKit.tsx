"use client";

import Link from "next/link";
import { useState } from "react";
import { postJSON } from "@/lib/api";
import EnvVal, { PctVal } from "./EnvVal";
import MetricTip, { type Tip } from "./MetricTip";
import DynamicLoader from "./DynamicLoader";
import type { Env } from "@/lib/api";
import { bigCrude, fmtDate, inr, pct } from "@/lib/format";

export function PageHeader({
  eyebrow,
  title,
  sub,
  right,
}: {
  eyebrow?: string;
  title: string;
  sub?: string;
  right?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 pb-7 pt-8">
      <div className="max-w-3xl">
        {eyebrow && (
          <div className="inline-flex items-center gap-2 rounded-md px-2.5 py-1 text-[10.5px] font-bold uppercase tracking-[0.18em] accent mb-3"
               style={{ border: "1px solid color-mix(in srgb, var(--accent) 32%, var(--line))",
                        background: "color-mix(in srgb, var(--accent) 9%, transparent)" }}>
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] inline-block" />
            {eyebrow}
          </div>
        )}
        <h1 className="text-[30px] sm:text-[38px] font-black leading-[1.03] tracking-tight">
          {title}
        </h1>
        {sub && <p className="muted text-[13.5px] leading-relaxed mt-3 max-w-2xl">{sub}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Link href="/calculators" className="btn-secondary !px-3.5 !py-2 !text-[12.5px]"
              title="Open every calculator in one hub">
          Calculators
        </Link>
        {right}
      </div>
    </div>
  );
}

export function SectionTitle({
  title,
  sub,
  right,
}: {
  title: string;
  sub?: string;
  right?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
      <div>
        <h2 className="text-[18px] sm:text-[20px] font-extrabold tracking-tight">{title}</h2>
        {sub && <p className="muted text-[12px] mt-1">{sub}</p>}
      </div>
      {right}
    </div>
  );
}

export function RefreshButton({ stage, label = "Refresh" }: { stage: string; label?: string }) {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <button
      disabled={busy}
      onClick={async () => {
        setBusy(true); setErr(null);
        try {
          await postJSON(`/refresh/${stage}`);
          setDone(true);
          setTimeout(() => window.location.reload(), 700);
        } catch (e: any) {
          setErr(String(e.message || e).slice(0, 120));
        }
        setBusy(false);
      }}
      className="btn-secondary !px-3.5 !py-2 !text-[12.5px]"
      title="Re-fetch fresh data from the free sources into the local store"
    >
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           strokeWidth="2" strokeLinecap="round" className={busy ? "animate-spin" : ""}>
        <path d="M21 12a9 9 0 1 1-2.6-6.4M21 3v6h-6" />
      </svg>
      {busy ? "Fetching…" : done ? "Done — reloading" : label}
      {err && <span className="text-[10px] text-down">{err}</span>}
    </button>
  );
}

export function Skeleton({ rows = 6, label }: { rows?: number; label?: string }) {
  return (
    <div className="space-y-2" aria-busy="true">
      <div className="card p-3.5 mb-2.5">
        <DynamicLoader size={36} label={label || "Loading desk"} status="Fetching the latest snapshot…" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton h-11" />
      ))}
    </div>
  );
}

/** Standard page-level loading block: animated mark + skeleton rows. */
export function LoadingBlock({
  label = "Loading",
  status = "Warming the engine…",
  rows = 4,
}: {
  label?: string;
  status?: string;
  rows?: number;
}) {
  return (
    <div className="card p-5">
      <DynamicLoader size={44} label={label} status={status} />
      <div className="mt-4">
        <Skeleton rows={rows} />
      </div>
    </div>
  );
}

export function ErrorBox({ message, stage }: { message: string; stage: string }) {
  return (
    <div className="card p-5 space-y-3" style={{ borderColor: "color-mix(in srgb, var(--warn) 35%, var(--line))" }}>
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-[var(--warn)]" />
        <div className="text-[13px] font-semibold">Couldn’t load right now</div>
      </div>
      <p className="muted text-[12.5px] leading-relaxed">
        {message} — the free sources are throttling or the store is still seeding.
        This resolves itself once the source answers or the seed finishes.
      </p>
      <RefreshButton stage={stage} label="Retry now" />
    </div>
  );
}

export type StatItem = {
  label: string;
  env?: Env;
  fmt?: (v: any) => string;
  hint?: string;
  tip?: Tip;
  emphasis?: boolean;
  sub?: string;
};

export function StatGrid({ items }: { items: StatItem[] }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-2.5">
      {items.map((it) => (
        <div key={it.label} className="card card-hover p-3.5" title={it.tip ? undefined : it.hint}>
          <div className="muted text-[10.5px] font-bold uppercase tracking-[0.13em] mb-1.5">
            {it.tip ? (
              <MetricTip label={it.label} tip={it.tip}>{it.label}</MetricTip>
            ) : it.label}
          </div>
          <div className={`font-bold ${it.emphasis ? "text-[22px]" : "text-[18px]"}`}>
            <EnvVal env={it.env} fmt={it.fmt || inr} />
          </div>
          {it.sub && <div className="muted text-[10.5px] mt-1">{it.sub}</div>}
        </div>
      ))}
    </div>
  );
}

export function MoverCard({ mover }: { mover: { symbol: string; name: string; last: any; changepct: any; href: string } }) {
  const up = (mover.changepct || 0) >= 0;
  return (
    <Link href={mover.href} className="card card-hover p-3.5 block">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[12.5px] font-bold truncate">{mover.symbol}</span>
        <span className={`chip !text-[9.5px] !py-0.5 ${up ? "chip-live" : ""}`}
              style={!up ? { color: "var(--down)", borderColor: "color-mix(in srgb, var(--down) 35%, var(--line))",
                             background: "color-mix(in srgb, var(--down) 10%, transparent)" } : undefined}>
          {pct(mover.changepct)}
        </span>
      </div>
      <div className="muted text-[11px] truncate mt-0.5">{mover.name}</div>
      <div className="flex items-baseline justify-between gap-2 mt-2.5">
        <span className="knum text-[15px] font-bold">{inr(mover.last)}</span>
        <span className={`text-[10.5px] font-semibold ${up ? "text-up" : "text-down"}`}>
          {up ? "▲" : "▼"}
        </span>
      </div>
    </Link>
  );
}

export { bigCrude, fmtDate, PctVal };
