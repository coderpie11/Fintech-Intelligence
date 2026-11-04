"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getJSON, type Env } from "@/lib/api";
import { inr, pct } from "@/lib/format";
import { ErrorBox, PageHeader, RefreshButton, Skeleton } from "@/components/PageKit";
import MarketClock from "@/components/MarketClock";
import MetricTip from "@/components/MetricTip";

type Idx = {
  slug: string; symbol: string; name: string; full_name: string; group?: string;
  last: Env; changepct: Env; prev_close: Env; day_range: Env; year_range: Env;
  pe: Env; pb: Env; dy: Env;
  constituents_count: number; fno_available: boolean; fno_symbol?: string;
  spark: number[]; live_source?: string; asof?: string;
};

const GROUPS = ["All", "Benchmark", "Broad", "Sectoral", "Thematic", "Volatility"];

function envVal<T = number>(e?: Env<T>): T | null {
  return e && e.value != null ? e.value : null;
}

function Spark({ points }: { points: number[] }) {
  if (!points || points.length < 2) {
    return <div className="h-9 rounded" style={{ background: "var(--surface-2)" }} />;
  }
  const W = 140, H = 38;
  const min = Math.min(...points), max = Math.max(...points);
  const span = max - min || 1;
  const x = (i: number) => (i / (points.length - 1)) * W;
  const y = (v: number) => H - 3 - ((v - min) / span) * (H - 6);
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p).toFixed(1)}`).join(" ");
  const up = points[points.length - 1] >= points[0];
  const color = up ? "var(--up)" : "var(--down)";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-9" preserveAspectRatio="none" aria-hidden>
      <path d={`${path} L${W},${H} L0,${H} Z`} fill={color} opacity="0.10" />
      <path d={path} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

function RangeBar({ last, low, high }: { last?: number | null; low?: number | null; high?: number | null }) {
  if (last == null || low == null || high == null || high <= low) {
    return <div className="h-1.5 rounded-full" style={{ background: "var(--line)" }} />;
  }
  const p = Math.max(0, Math.min(100, ((last - low) / (high - low)) * 100));
  return (
    <div className="relative h-1.5 rounded-full" style={{ background: "var(--line)" }}>
      <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${p}%`, background: "var(--accent)", opacity: 0.5 }} />
      <div className="absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full"
           style={{ left: `calc(${p}% - 5px)`, background: "var(--accent)", boxShadow: "0 0 0 2px var(--surface)" }} />
    </div>
  );
}

export default function IndicesPage() {
  const [data, setData] = useState<{ indices: Idx[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [group, setGroup] = useState("All");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<"default" | "gainers" | "losers">("default");

  useEffect(() => {
    getJSON(`/indices?expand=true`)
      .then((r) => setData(r))
      .catch((e) => setErr(String(e.message || e)));
  }, []);

  const rows = useMemo(() => {
    let list = data?.indices || [];
    if (group !== "All") list = list.filter((i) => i.group === group);
    if (q.trim()) {
      const needle = q.trim().toLowerCase();
      list = list.filter((i) => (i.name + " " + i.symbol).toLowerCase().includes(needle));
    }
    if (sort === "gainers") list = [...list].sort((a, b) => (envVal(b.changepct) || 0) - (envVal(a.changepct) || 0));
    if (sort === "losers") list = [...list].sort((a, b) => (envVal(a.changepct) || 0) - (envVal(b.changepct) || 0));
    return list;
  }, [data, group, q, sort]);

  const all = data?.indices || [];
  const advancing = all.filter((i) => (envVal(i.changepct) || 0) > 0).length;
  const declining = all.filter((i) => (envVal(i.changepct) || 0) < 0).length;
  const best = [...all].sort((a, b) => (envVal(b.changepct) || 0) - (envVal(a.changepct) || 0))[0];
  const worst = [...all].sort((a, b) => (envVal(a.changepct) || 0) - (envVal(b.changepct) || 0))[0];

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6">
      <PageHeader
        eyebrow="Indices · GIFT corridor · India VIX"
        title="Indices Desk"
        sub="All 18 benchmark, broad, sectoral and thematic indices with live last, day and 52-week ranges, five-year history, constituents and the F&O tab where it applies."
        right={<><MarketClock /><RefreshButton stage="indices" /></>}
      />

      {err && <ErrorBox message={err} stage="indices" />}
      {!data && !err && <Skeleton rows={8} />}

      {data && (
        <>
          {/* summary strip */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 mb-5">
            {[
              { k: "Indices tracked", v: String(all.length), sub: `${all.reduce((a, i) => a + i.constituents_count, 0)} constituents`, tone: "accent" },
              { k: "Advancing", v: String(advancing), sub: "positive on the day", tone: "up" },
              { k: "Declining", v: String(declining), sub: "negative on the day", tone: "down" },
              { k: "Best / worst", v: best ? pct(envVal(best.changepct)) : "—", sub: worst ? `${best?.name} · ${worst.name} ${pct(envVal(worst.changepct))}` : "—", tone: "warn" },
            ].map((s) => (
              <div key={s.k} className="card p-3.5">
                <div className="muted text-[10px] font-bold uppercase tracking-[0.14em]">{s.k}</div>
                <div className={`knum text-[22px] font-black mt-1 ${s.tone === "up" ? "text-up" : s.tone === "down" ? "text-down" : s.tone === "warn" ? "text-[var(--warn)]" : "accent"}`}>{s.v}</div>
                <div className="muted text-[10.5px] mt-0.5 truncate">{s.sub}</div>
              </div>
            ))}
          </div>

          {/* filters */}
          <div className="flex flex-wrap items-center gap-2 mb-4">
            <div className="flex flex-wrap items-center gap-1.5">
              {GROUPS.map((g) => (
                <button key={g} onClick={() => setGroup(g)}
                        className={`rounded-md px-2.5 py-1.5 text-[11.5px] font-semibold transition-colors ${group === g ? "text-white" : "muted"}`}
                        style={group === g ? { background: "var(--accent)", color: "#041018" } : { border: "1px solid var(--line)" }}>
                  {g}
                </button>
              ))}
            </div>
            <div className="ml-auto flex items-center gap-2">
              <select value={sort} onChange={(e) => setSort(e.target.value as any)}
                      className="rounded-md px-2.5 py-2 text-[11.5px] font-semibold"
                      style={{ background: "var(--surface)", border: "1px solid var(--line)", color: "var(--ink)" }}>
                <option value="default">Declared order</option>
                <option value="gainers">Biggest gainers</option>
                <option value="losers">Biggest losers</option>
              </select>
              <div className="flex items-center gap-2 rounded-md px-2.5 py-2"
                   style={{ background: "var(--surface)", border: "1px solid var(--line)" }}>
                <span className="muted text-[12px]">⌕</span>
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter indices…"
                       className="bg-transparent text-[12px] outline-none w-[150px]"
                       style={{ color: "var(--ink)" }} />
              </div>
            </div>
          </div>

          {/* index cards */}
          <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-2.5 pb-14">
            {rows.map((i) => {
              const up = (envVal(i.changepct) || 0) >= 0;
              const lo = i.year_range?.value?.[0];
              const hi = i.year_range?.value?.[1];
              return (
                <Link key={i.slug} href={`/indices/${i.slug}`} className="card card-hover p-4 block">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-[13.5px] font-bold truncate">{i.name}</span>
                        {i.fno_available && <span className="chip !text-[8.5px] !py-0.5">F&O</span>}
                      </div>
                      <div className="muted text-[10.5px] mt-0.5 truncate">
                        {i.group || "Index"} · {i.constituents_count} constituents
                      </div>
                    </div>
                    <span className={`chip !text-[9px] !py-0.5 ${up ? "chip-live" : ""}`}
                          style={!up ? { color: "var(--down)", borderColor: "color-mix(in srgb, var(--down) 35%, var(--line))", background: "color-mix(in srgb, var(--down) 10%, transparent)" } : undefined}>
                      {pct(envVal(i.changepct))}
                    </span>
                  </div>

                  <div className="flex items-end justify-between gap-3 mt-3">
                    <div>
                      <div className="knum text-[24px] font-black leading-none">{inr(envVal(i.last))}</div>
                      <div className="muted text-[10px] mt-1">
                        Prev {inr(envVal(i.prev_close))} ·{" "}
                        <MetricTip label="P/E" tip={{
                          meaning: "Price-to-Earnings for the index: the weighted price divided by the weighted trailing earnings of its constituents.",
                          formula: "Index P/E = Σ (weight × market cap) ÷ Σ (weight × earnings)",
                        }}>P/E</MetricTip>{" "}
                        {envVal(i.pe) ?? "—"}
                      </div>
                    </div>
                    <div className="w-[44%]">
                      <Spark points={i.spark} />
                    </div>
                  </div>

                  <div className="mt-3">
                    <div className="flex justify-between muted text-[9.5px] mb-1.5">
                      <span>{inr(lo)}</span>
                      <span>
                        <MetricTip label="52W range" tip={{
                          meaning: "The index's lowest and highest level in the last 52 weeks; the bar shows where today sits inside that band.",
                          formula: "Position % = (Last − 52W low) ÷ (52W high − 52W low) × 100",
                        }}>52W range</MetricTip>
                      </span>
                      <span>{inr(hi)}</span>
                    </div>
                    <RangeBar last={envVal(i.last)} low={lo} high={hi} />
                  </div>
                </Link>
              );
            })}
            {rows.length === 0 && (
              <div className="card p-8 text-center muted text-[13px] sm:col-span-2 xl:col-span-3">
                No index matches this filter.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
