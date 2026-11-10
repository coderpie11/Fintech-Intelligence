"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { getJSON, type Env } from "@/lib/api";
import { fmtDate, inr, pct } from "@/lib/format";
import { isMarketOpenIST } from "@/lib/market";
import {
  ErrorBox, PageHeader, RefreshButton, SectionTitle, Skeleton, StatGrid,
} from "@/components/PageKit";
import MetricTip, { type Tip } from "@/components/MetricTip";
import LineChart, { type ChartHoverPoint } from "@/components/LineChart";
import FnoTab from "@/components/FnoTab";
import Tabs from "@/components/Tabs";
import WatchlistButton from "@/components/WatchlistButton";

type Const = {
  symbol: string;
  name: string;
  sector: string | null;
  weight: number | null;
  last: number | null;
  changepct: number | null;
  year_high: number | null;
  year_low: number | null;
  pe: number | null;
  market_cap: number | null;
  href: string;
};

type Det = {
  symbol: string;
  name: string;
  full_name: string;
  slug: string;
  group: string | null;
  about: string;
  last: Env;
  change: Env;
  changepct: Env;
  open: Env;
  prev_close: Env;
  day_range: Env<[number, number]>;
  day_high: Env;
  day_low: Env;
  year_range: Env<[number, number]>;
  high_52w: Env;
  low_52w: Env;
  pe: Env;
  pb: Env;
  dy: Env;
  breadth: { advances: Env; declines: Env };
  returns: Record<string, Env>;
  stats: Record<string, Env>;
  fno_tab_available: boolean;
  fno_symbol: string | null;
  constituents: Const[];
  constituents_count: number;
  weight_basis: string | null;
  constituents_source: string | null;
  history: { date: string; close: number; open?: number; high?: number; low?: number }[];
  history_points: number;
  history_source: string | null;
  live_source: string | null;
  live_time?: string | null;
  source_note: string | null;
  asof: string | null;
  level_date?: string | null;
  fetched_at?: string | null;
  valuation_source?: { kind: string; note: string };
  data_note: Env;
};

const TIPS: Record<string, Tip> = {
  pe: {
    meaning:
      "How many rupees you pay for every ₹1 of yearly profit made by all the companies in this index. A high number means expectations are high.",
    formula: "Index P/E = total value of companies ÷ their total yearly profit",
    example: "P/E 22 means ₹22 paid for every ₹1 of yearly profit.",
  },
  pb: {
    meaning:
      "The market value compared with the accounting net worth of all the companies in the index. Handy for banks and asset-heavy sectors.",
    formula: "Index P/B = total value ÷ total net worth",
    example: "P/B 3.4 means the market values the index at 3.4× its net assets.",
  },
  dy: {
    meaning: "The cash dividend paid by the companies each year as a percent of the index level. Like rent on the index.",
    formula: "Dividend yield = yearly dividend ÷ index level × 100",
    example: "A 1.25% yield on a 23,000 index is about ₹287 a year per index unit.",
  },
  cagr: {
    meaning: "The steady yearly growth rate that takes the start value to today's value. Makes long periods easy to compare.",
    formula: "CAGR = (End ÷ Start) to the power of (1 ÷ years) − 1",
    example: "10,000 growing to 16,105 over 5 years is about 10% a year.",
  },
  vol: {
    meaning: "How bumpy the index is day to day, shown as a yearly number. It measures the size of the swings, not the direction.",
    formula: "Yearly volatility ≈ size of daily moves scaled to a year",
    example: "14% volatility means most years land within about ±14% of the average.",
  },
  mdd: {
    meaning: "The worst fall from a high to a low. It tells you how bad it felt, not what you earned.",
    formula: "Max fall = worst drop from a running high",
    example: "A −38% fall means an investor at the top was once down 38%.",
  },
  range52: {
    meaning: "The lowest and highest level in the last year, and where today sits between them. Near the high shows strength; near the low shows weakness.",
    formula: "Position = (today − 52-week low) ÷ (52-week high − low) × 100",
    example: "A level of 23,000 inside 22,180–26,373 sits about 20% up the yearly range.",
  },
  weight: {
    meaning: "How big one company's slice is in the index. Here it is an estimate from free-float size, not the official published weight.",
    formula: "Weight = one company's free-float value ÷ total of all ÷ 100",
    example: "A ₹8 lakh crore free-float in a ₹100 lakh crore index is about 8%.",
  },
};

function envNum<T = number>(e?: Env<T>): T | null {
  return e && e.value != null ? e.value : null;
}

function RangeBar({
  last, low, high,
}: { last?: number | null; low?: number | null; high?: number | null }) {
  if (last == null || low == null || high == null || high <= low) {
    return <div className="h-1.5 rounded-full" style={{ background: "var(--line)" }} />;
  }
  const p = Math.max(0, Math.min(100, ((last - low) / (high - low)) * 100));
  return (
    <div className="relative h-1.5 rounded-full" style={{ background: "var(--line)" }}>
      <div className="absolute inset-y-0 left-0 rounded-full"
           style={{ width: `${p}%`, background: "var(--accent)", opacity: 0.45 }} />
      <div className="absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full"
           style={{ left: `calc(${p}% - 5px)`, background: "var(--accent)",
                    boxShadow: "0 0 0 2px var(--surface)" }} />
    </div>
  );
}

const PERIODS: { key: string; label: string; tip: string }[] = [
  { key: "1w", label: "1 week", tip: "Simple price return over the last 5 trading sessions." },
  { key: "1m", label: "1 month", tip: "Simple price return over the last 21 trading sessions." },
  { key: "3m", label: "3 months", tip: "Simple price return over the last 63 trading sessions." },
  { key: "6m", label: "6 months", tip: "Simple price return over the last 126 trading sessions." },
  { key: "1y", label: "1 year", tip: "Simple price return over the last 252 trading sessions." },
  { key: "3y", label: "3Y CAGR", tip: "Compound annual growth over roughly 756 sessions." },
  { key: "5y", label: "5Y CAGR", tip: "Compound annual growth across the full stored history." },
];

export default function IndexDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const [d, setD] = useState<Det | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState("overview");
  const [sort, setSort] = useState<"weight" | "change" | "name">("weight");
  const [q, setQ] = useState("");
  const [intraday, setIntraday] = useState<any>(null);
  const [scrub, setScrub] = useState<ChartHoverPoint | null>(null);

  const openFno = () => {
    setTab("fno");
    setTimeout(() => {
      document.getElementById("fno-section-anchor")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 60);
  };

  useEffect(() => {
    let live = true;
    setD(null);
    setErr(null);
    setScrub(null);

    const load = (initial: boolean) => {
      Promise.allSettled([
        getJSON<Det>(`/indices/${slug}`),
        getJSON(`/indices/${slug}/intraday`),
      ]).then(([det, intra]) => {
        if (!live) return;
        if (det.status === "fulfilled") {
          setD(det.value);
          setErr(null);
        } else if (initial) {
          setErr(String((det.reason as any)?.message || det.reason));
        }
        if (intra.status === "fulfilled") setIntraday(intra.value);
        else if (initial) setIntraday(null);
      });
    };

    load(true);
    const id = window.setInterval(() => {
      if (isMarketOpenIST()) load(false);
    }, 15_000);
    return () => { live = false; window.clearInterval(id); };
  }, [slug]);

  const intradayPoints = useMemo(
    () => (intraday?.points || []).map((p: any) => ({
      date: p.date, close: p.c, open: p.o, high: p.h, low: p.l,
      time: p.time, datetime: p.datetime, volume: p.v,
    })),
    [intraday],
  );

  const constituents = useMemo(() => {
    let list = [...(d?.constituents || [])];
    if (q.trim()) {
      const n = q.trim().toLowerCase();
      list = list.filter((c) =>
        (c.symbol + " " + c.name + " " + (c.sector || "")).toLowerCase().includes(n));
    }
    if (sort === "weight") list.sort((a, b) => (b.weight ?? -1) - (a.weight ?? -1));
    if (sort === "change") list.sort((a, b) => (b.changepct ?? -999) - (a.changepct ?? -999));
    if (sort === "name") list.sort((a, b) => a.symbol.localeCompare(b.symbol));
    return list;
  }, [d, sort, q]);

  if (err) {
    return (
      <div className="mx-auto max-w-[1600px] px-4 sm:px-6 py-8">
        <ErrorBox message={err} stage="indices" />
        <Link href="/indices" className="btn-secondary mt-4">← Back to all indices</Link>
      </div>
    );
  }

  if (!d) {
    return (
      <div className="mx-auto max-w-[1600px] px-4 sm:px-6 py-8 space-y-3">
        <div className="skeleton h-16" />
        <Skeleton rows={6} />
      </div>
    );
  }

  const last = envNum(d.last);
  const liveChange = envNum(d.change)
    ?? (last != null && envNum(d.prev_close) != null ? last - (envNum(d.prev_close) as number) : null);
  const shownLast = scrub?.price ?? last;
  const shownChange = scrub ? scrub.change : liveChange;
  const shownPct = scrub ? scrub.pctChange : envNum(d.changepct);
  const up = (shownChange ?? 0) >= 0;
  const yrLow = d.year_range?.value?.[0] ?? null;
  const yrHigh = d.year_range?.value?.[1] ?? null;
  const dayLow = d.day_range?.value?.[0] ?? null;
  const dayHigh = d.day_range?.value?.[1] ?? null;
  const isVix = slug === "india-vix";

  // VIX context — mean level and rank inside its own last year.
  const vixWindow = (d.history || []).slice(-252).map((h) => h.close).filter(Number.isFinite);
  const vixAvg = vixWindow.length
    ? vixWindow.reduce((a, b) => a + b, 0) / vixWindow.length
    : null;
  const vixPctile = vixWindow.length && last != null
    ? (vixWindow.filter((v) => v <= last).length / vixWindow.length) * 100
    : null;

  const tabs = [
    { key: "overview", label: "Overview" },
    ...(d.constituents_count > 0
      ? [{ key: "constituents", label: `Constituents (${d.constituents_count})` }]
      : []),
    ...(d.fno_tab_available
      ? [{ key: "fno", label: isVix ? "Volatility" : "F&O" }]
      : []),
    { key: "sources", label: "Data & sources" },
  ];

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 pb-16">
      {/* breadcrumb */}
      <div className="pt-5 flex items-center gap-2 muted text-[11.5px]">
        <Link href="/indices" className="hover:underline">Indices</Link>
        <span className="opacity-40">/</span>
        <span style={{ color: "var(--ink)" }} className="font-semibold">{d.name}</span>
      </div>

      <PageHeader
        eyebrow={`${d.group || "Index"} · ${d.symbol}`}
        title={d.name}
        sub={d.about}
        right={
          <>
            <WatchlistButton symbol={d.fno_symbol || d.symbol || d.slug} kind="INDEX" href={`/indices/${d.slug}`} />
            <RefreshButton stage="indices" />
            {d.fno_tab_available && (
              <button onClick={openFno} className="btn-primary !py-2 !text-[12.5px]">
                {isVix ? "Open VIX calculator" : "Open F&O tab"}
              </button>
            )}
          </>
        }
      />

      {/* price + chart panel */}
      <div className="grid lg:grid-cols-[1fr_320px] gap-3 mb-4">
        <div className="card p-4 sm:p-5">
          <div className="flex flex-wrap items-end justify-between gap-3 mb-2">
            <div>
              <div className="muted text-[10px] font-bold uppercase tracking-[0.16em]">
                {scrub ? "Chart point" : "Live level"}
                <span className="ml-2 normal-case tracking-normal opacity-80">
                  {scrub ? "· move cursor off chart to return live" : ""}
                </span>
              </div>
              <div className="flex flex-wrap items-end gap-3 mt-1">
                <span className="knum text-[34px] font-black leading-none">{inr(shownLast)}</span>
                <span className={`knum text-[15px] font-bold ${up ? "text-up" : "text-down"}`}>
                  {shownChange != null && shownChange > 0 ? "+" : ""}{inr(shownChange)}
                  <span className="ml-2">{pct(shownPct)}</span>
                </span>
                <span className={`chip !text-[9px] ${scrub ? "chip-warn" : "chip-live"}`}>
                  {scrub ? "SCRUBBING" : "LIVE"}
                </span>
              </div>
              <div className="muted text-[11px] mt-1.5">
                {scrub
                  ? `${scrub.label} · chart candle`
                  : (d.live_time || (d.asof ? `Session close ${fmtDate(d.asof)}` : "Latest available session"))}
                {d.live_source && !scrub ? ` · ${d.live_source}` : ""}
              </div>
              {d.fetched_at && !scrub && (
                <div className="muted text-[10.5px] mt-0.5 opacity-80">
                  Last refreshed {fmtDate(d.fetched_at)}
                </div>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="chip !text-[9.5px]">{d.group || "Index"}</span>
              {d.fno_tab_available && <span className="chip chip-active !text-[9.5px]">F&amp;O</span>}
              {isVix && <span className="chip chip-warn !text-[9.5px]">Volatility gauge</span>}
            </div>
          </div>

          <LineChart
            points={d.history || []}
            height={330}
            defaultRange="1D"
            intradayPoints={intradayPoints}
            intradaySource={intraday?.source}
            prevClose={envNum(d.prev_close)}
            onHoverPointChange={setScrub}
            title={`${d.name} · price history`}
          />
        </div>

        <aside className="card p-4 sm:p-5 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            {([
              { label: "Open", env: d.open },
              { label: "Prev close", env: d.prev_close },
              { label: "Day high", env: d.day_high },
              { label: "Day low", env: d.day_low },
            ] as { label: string; env: Env }[]).map((row) => (
              <div key={row.label} className="rounded-md px-2.5 py-2"
                   style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                <div className="muted text-[9px] font-bold uppercase tracking-wider">{row.label}</div>
                <div className="knum text-[13px] font-bold mt-0.5">
                  {envNum(row.env) != null ? inr(envNum(row.env)) : "—"}
                </div>
              </div>
            ))}
          </div>

          <div>
            <div className="flex items-center justify-between muted text-[10px] mb-1.5">
              <span className="font-bold uppercase tracking-[0.13em]">
                <MetricTip label="52-week range" tip={TIPS.range52} />
              </span>
              <span className="knum">{last != null && yrLow != null && yrHigh != null
                ? `${Math.max(0, Math.min(100, ((last - yrLow) / (yrHigh - yrLow || 1)) * 100)).toFixed(0)}%`
                : "—"}</span>
            </div>
            <RangeBar last={last} low={yrLow} high={yrHigh} />
            <div className="flex justify-between knum muted text-[10px] mt-1.5">
              <span>{inr(yrLow)}</span>
              <span>{inr(yrHigh)}</span>
            </div>
          </div>

          <div>
            <div className="flex justify-between muted text-[10px] mb-1.5">
              <span className="font-bold uppercase tracking-[0.13em]">Day range</span>
              <span className="knum">
                {dayLow != null && dayHigh != null
                  ? `${inr(dayLow)} – ${inr(dayHigh)}` : "—"}
              </span>
            </div>
            <RangeBar last={last} low={dayLow} high={dayHigh} />
          </div>

          {!isVix && (
            <div className="grid grid-cols-3 gap-2 pt-1">
              {([
                { label: "P/E", env: d.pe, tip: TIPS.pe },
                { label: "P/B", env: d.pb, tip: TIPS.pb },
                { label: "Div yield", env: d.dy, tip: TIPS.dy },
              ] as { label: string; env: Env; tip: Tip }[]).map((row) => (
                <div key={row.label} className="rounded-md px-2.5 py-2"
                     style={{ border: "1px solid var(--line)" }}>
                  <div className="muted text-[9px] font-bold uppercase tracking-wider">
                    <MetricTip label={row.label} tip={row.tip} />
                  </div>
                  <div className="knum text-[13px] font-bold mt-0.5">
                    {envNum(row.env) != null ? row.env.value : "—"}
                    {row.label === "Div yield" && envNum(row.env) != null ? "%" : ""}
                  </div>
                </div>
              ))}
            </div>
          )}

          {d.breadth && (envNum(d.breadth.advances) != null || envNum(d.breadth.declines) != null) && (
            <div className="rounded-md p-2.5" style={{ border: "1px solid var(--line)" }}>
              <div className="muted text-[9px] font-bold uppercase tracking-wider mb-1">
                Internal breadth
              </div>
              <div className="flex items-center gap-3 text-[12px] font-bold">
                <span className="text-up">{envNum(d.breadth.advances) ?? "—"} advancing</span>
                <span className="text-down">{envNum(d.breadth.declines) ?? "—"} declining</span>
              </div>
            </div>
          )}
        </aside>
      </div>

      <div className="mb-5">
        <Tabs tabs={tabs} active={tab} onChange={(k) => (k === "fno" ? openFno() : setTab(k))} />
      </div>

      {/* ---------------- OVERVIEW ---------------- */}
      {tab === "overview" && (
        <div className="space-y-6">
          <section>
            <SectionTitle
              title={isVix ? "VIX change ladder" : "Performance ladder"}
              sub={
                isVix
                  ? "VIX is a volatility level, not a price, so compounding it over years is meaningless. Only the horizon changes below are shown."
                  : "Simple price returns up to one year; 3-year and 5-year figures are compound annual growth rates."
              }
            />
            <StatGrid
              items={isVix
                ? PERIODS.filter((p) => p.key !== "3y" && p.key !== "5y").map((p) => ({
                    label: p.label,
                    env: d.returns?.[p.key],
                    fmt: (v: number) => pct(v),
                    tip: { meaning: p.tip, formula: "Return = (End ÷ Start − 1) × 100" },
                  }))
                : PERIODS.map((p) => ({
                    label: p.label,
                    env: d.returns?.[p.key],
                    fmt: (v: number) => pct(v),
                    tip: {
                      meaning: p.tip,
                      formula: p.key.endsWith("y") && p.key !== "1y"
                        ? "CAGR = (End ÷ Start)^(1 ÷ Years) − 1"
                        : "Return = (End ÷ Start − 1) × 100",
                    },
                  }))}
            />
          </section>

          <section>
            <SectionTitle
              title="Risk statistics"
              sub="Computed by the platform from the stored daily closes — not borrowed from a data vendor."
            />
            <StatGrid
              items={[
                {
                  label: "Volatility 1Y",
                  env: d.stats?.vol_1y,
                  fmt: (v: number) => `${v}%`,
                  tip: TIPS.vol,
                  sub: "annualised daily-return swing",
                },
                {
                  label: "Volatility 3Y",
                  env: d.stats?.vol_3y,
                  fmt: (v: number) => `${v}%`,
                  tip: TIPS.vol,
                  sub: "three-year annualised",
                },
                {
                  label: "Max drawdown 1Y",
                  env: d.stats?.max_dd_1y,
                  fmt: (v: number) => pct(v),
                  tip: TIPS.mdd,
                  sub: "worst peak-to-trough fall",
                },
                {
                  label: "Max drawdown 5Y",
                  env: d.stats?.max_dd_5y,
                  fmt: (v: number) => pct(v),
                  tip: TIPS.mdd,
                  sub: "full stored history",
                },
              ]}
            />
          </section>

          {isVix && (
            <section>
              <SectionTitle
                title="Where this VIX sits"
                sub="Level context computed from the stored daily VIX series, so a reading means something."
              />
              <StatGrid
                items={[
                  {
                    label: "1Y average",
                    env: vixAvg != null ? { value: vixAvg, status: "REPORTED", note: "" } : undefined,
                    fmt: (v: number) => v.toFixed(2),
                    sub: "mean VIX over the last 252 sessions",
                  },
                  {
                    label: "1Y percentile",
                    env: vixPctile != null ? { value: vixPctile, status: "REPORTED", note: "" } : undefined,
                    fmt: (v: number) => `${v.toFixed(0)}%`,
                    sub: "share of the last year spent below today",
                  },
                  {
                    label: "52W high",
                    env: d.high_52w,
                    fmt: (v: number) => v.toFixed(2),
                  },
                  {
                    label: "52W low",
                    env: d.low_52w,
                    fmt: (v: number) => v.toFixed(2),
                  },
                ]}
              />
            </section>
          )}

          {!isVix && (
            <section>
              <SectionTitle
                title="Valuation"
                sub={d.valuation_source?.note
                  || "Exchange-published ratios for the index basket. Hover any label to decode the maths."}
              />
              <StatGrid
                items={[
                  { label: "Index P/E", env: d.pe, fmt: (v: number) => String(v), tip: TIPS.pe },
                  { label: "Index P/B", env: d.pb, fmt: (v: number) => String(v), tip: TIPS.pb },
                  { label: "Dividend yield", env: d.dy, fmt: (v: number) => `${v}%`, tip: TIPS.dy },
                  {
                    label: "History depth",
                    env: { value: d.history_points, status: "REPORTED", note: "" },
                    fmt: (v: number) => `${v.toLocaleString("en-IN")} sessions`,
                    sub: d.history_source || undefined,
                  },
                ]}
              />
            </section>
          )}

          {isVix && (
            <section className="card p-4 sm:p-5">
              <SectionTitle
                title="What INDIA VIX actually measures"
                sub="It is not a company index and has no constituents or valuation ratios."
              />
              <p className="muted text-[13px] leading-relaxed max-w-3xl">
                INDIA VIX is computed by NSE from the prices of NIFTY options across strikes.
                It expresses the market's expected annualised volatility over the next 30 days.
                A reading of 15 implies roughly a ±15% annualised swing — about ±4.3% over a
                month if volatility stays at that level. Rising VIX means option buyers are
                paying more for protection; falling VIX means complacency.
              </p>
              <button onClick={openFno} className="btn-secondary mt-4 !py-2 !text-[12.5px]">
                Open the VIX swing calculator →
              </button>
            </section>
          )}
        </div>
      )}

      {/* ---------------- CONSTITUENTS ---------------- */}
      {tab === "constituents" && (
        <section className="card overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
               style={{ borderBottom: "1px solid var(--line)" }}>
            <div>
              <h2 className="text-[14px] font-extrabold">Constituents &amp; weightage</h2>
              <p className="muted text-[11px] mt-0.5">
                {d.constituents_count} members ·{" "}
                <MetricTip label="weight" tip={TIPS.weight}>
                  weight basis
                </MetricTip>
                {" "}— {d.weight_basis || "free-float market-cap estimate"}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-2 rounded-md px-2.5 py-1.5"
                   style={{ border: "1px solid var(--line)" }}>
                <span className="muted text-[12px]">⌕</span>
                <input value={q} onChange={(e) => setQ(e.target.value)}
                       placeholder="Filter constituents…"
                       className="bg-transparent text-[12px] outline-none w-[160px]"
                       style={{ color: "var(--ink)" }} />
              </div>
              <select value={sort} onChange={(e) => setSort(e.target.value as any)}
                      className="rounded-md px-2.5 py-1.5 text-[11.5px] font-semibold"
                      style={{ background: "var(--surface)", border: "1px solid var(--line)",
                               color: "var(--ink)" }}>
                <option value="weight">By weight</option>
                <option value="change">By day change</option>
                <option value="name">By symbol</option>
              </select>
            </div>
          </div>

          {d.constituents_count === 0 ? (
            <div className="px-4 py-12 text-center">
              <div className="text-[13px] font-semibold">Constituents not published for this index</div>
              <p className="muted text-[12px] mt-1.5 max-w-xl mx-auto leading-relaxed">
                {isVix
                  ? "INDIA VIX is derived from NIFTY option prices, so it has no member companies."
                  : "NSE's free constituent feed did not return a member list for this index. The platform shows nothing rather than inventing weights."}
              </p>
            </div>
          ) : (
            <div className="scroll-x">
              <table className="w-full min-w-[860px] border-collapse">
                <thead>
                  <tr>
                    <th className="table-head text-left px-4 py-2.5 w-[30%]">Company</th>
                    <th className="table-head text-left px-3 py-2.5">Sector</th>
                    <th className="table-head text-right px-3 py-2.5">Weight</th>
                    <th className="table-head text-right px-3 py-2.5">Last</th>
                    <th className="table-head text-right px-3 py-2.5">Day</th>
                    <th className="table-head text-left px-3 py-2.5 w-[19%]">52-week range</th>
                    <th className="table-head text-right px-4 py-2.5">P/E</th>
                  </tr>
                </thead>
                <tbody>
                  {constituents.map((c) => {
                    const cUp = (c.changepct || 0) >= 0;
                    return (
                      <tr key={c.symbol} className="table-row">
                        <td className="px-4 py-2.5">
                          <Link href={c.href} className="group block min-w-0">
                            <span className="block text-[12.5px] font-bold group-hover:text-[var(--accent)] truncate">
                              {c.symbol}
                            </span>
                            <span className="block muted text-[10.5px] truncate">{c.name}</span>
                          </Link>
                        </td>
                        <td className="px-3 py-2.5">
                          <span className="muted text-[11px] line-clamp-1">{c.sector || "—"}</span>
                        </td>
                        <td className="px-3 py-2.5 text-right">
                          <div className="inline-flex flex-col items-end gap-1">
                            <span className="knum text-[12px] font-bold">
                              {c.weight != null ? `${c.weight.toFixed(2)}%` : "—"}
                            </span>
                            <span className="block h-1 w-14 rounded-full overflow-hidden"
                                  style={{ background: "var(--line)" }}>
                              <span className="block h-full rounded-full"
                                    style={{ width: `${Math.min(100, (c.weight || 0) * 6)}%`,
                                             background: "var(--accent)" }} />
                            </span>
                          </div>
                        </td>
                        <td className="px-3 py-2.5 text-right knum text-[12px] font-semibold">
                          {inr(c.last)}
                        </td>
                        <td className={`px-3 py-2.5 text-right knum text-[12px] font-bold ${cUp ? "text-up" : "text-down"}`}>
                          {pct(c.changepct)}
                        </td>
                        <td className="px-3 py-2.5">
                          <RangeBar last={c.last} low={c.year_low} high={c.year_high} />
                          <div className="flex justify-between knum muted text-[9px] mt-1">
                            <span>{inr(c.year_low)}</span>
                            <span>{inr(c.year_high)}</span>
                          </div>
                        </td>
                        <td className="px-4 py-2.5 text-right knum text-[12px]">
                          {c.pe != null ? c.pe.toFixed(1) : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {constituents.length === 0 && (
                <div className="px-4 py-8 text-center muted text-[12px]">
                  No constituent matches this filter.
                </div>
              )}
            </div>
          )}

          <div className="px-4 py-2.5 muted text-[10.5px] flex flex-wrap items-center gap-x-4 gap-y-1"
               style={{ borderTop: "1px solid var(--line)", background: "var(--surface-2)" }}>
            <span>Source: {d.constituents_source || "NSE constituent feed"}</span>
            <span className="opacity-40">·</span>
            <span>Weights are estimates, not official index-provider weights.</span>
          </div>
        </section>
      )}

      {/* ---------------- F&O ---------------- */}
      {tab === "fno" && d.fno_tab_available && d.fno_symbol && (
        <div id="fno-section-anchor" className="scroll-mt-24">
        <section>
          <SectionTitle
            title={`${d.name} derivatives`}
            sub={
              isVix
                ? "VIX has no option chain — this tab converts the reading into expected NIFTY swing ranges."
                : slug === "sensex"
                ? "BSE does not expose a free option chain here, so the platform models it with its own Black-Scholes engine around the live spot."
                : "Live NSE option chain with platform-computed Greeks and probability of profit."
            }
          />
          <FnoTab underlying={d.fno_symbol} />
        </section>
        </div>
      )}

      {/* ---------------- SOURCES ---------------- */}
      {tab === "sources" && (
        <section className="grid md:grid-cols-2 gap-3">
          <div className="card p-4">
            <div className="text-[13px] font-bold mb-2.5">Where these numbers come from</div>
            <dl className="space-y-2 text-[12px]">
              {[
                ["Index symbol", d.symbol],
                ["Price source", d.live_source || "—"],
                ["History source", d.history_source || "—"],
                ["History depth", `${d.history_points.toLocaleString("en-IN")} daily sessions`],
                ["Constituent source", d.constituents_source || "—"],
                ["Last data stamp", d.asof ? fmtDate(d.asof) : "—"],
              ].map(([k, v]) => (
                <div key={k} className="flex items-start justify-between gap-4">
                  <dt className="muted">{k}</dt>
                  <dd className="text-right font-semibold" style={{ color: "var(--ink)" }}>{v}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="card p-4 space-y-3">
            <div className="text-[13px] font-bold">Honesty notes</div>
            {d.source_note && (
              <p className="muted text-[12px] leading-relaxed">{d.source_note}</p>
            )}
            <p className="muted text-[12px] leading-relaxed">
              {d.weight_basis ||
                "Constituent weights, where shown, are free-float market-cap estimates computed from member data — not the official weights published by NSE or BSE."}
            </p>
            <p className="muted text-[12px] leading-relaxed">
              {d.data_note?.value ||
                "Prices are indicative and may update with a lag. Nothing on this page is a buy or sell recommendation."}
            </p>
          </div>
        </section>
      )}
    </div>
  );
}
