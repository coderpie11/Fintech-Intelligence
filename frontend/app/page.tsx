"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getJSON, type Env } from "@/lib/api";
import { fmtDate, inr, pct } from "@/lib/format";
import { SectionTitle } from "@/components/PageKit";
import MarketClock from "@/components/MarketClock";
import LineChart from "@/components/LineChart";
import MetricTip from "@/components/MetricTip";

type Idx = {
  slug: string; symbol: string; name: string; group?: string;
  last: Env; changepct: Env; prev_close: Env;
  year_range: Env; day_range: Env;
  constituents_count: number; fno_available: boolean; fno_symbol?: string;
  pe: Env; pb: Env; dy: Env; spark: number[];
  asof?: string; live_source?: string;
};

type Counts = {
  indices: number; constituents: number; equities: number; funds: number;
  etfs: number; bonds: number; events: number; ipos: number; reits: number;
  commodities: number; sandbox_orders: number;
};

const HTIPS: Record<string, { meaning: string; formula?: string; example?: string }> = {
  open: { meaning: "The first price of today's session, at 9:15 am.", formula: "Open = first trade of the day" },
  prev: { meaning: "Yesterday's closing level. Today's change is measured against this.", formula: "Change % = (Today ÷ Yesterday − 1) × 100" },
  high: { meaning: "The highest level in the last 52 weeks (one year).",
          example: "A 52-week high of 26,373 with today's 23,346 means the index is well below its yearly peak." },
  low: { meaning: "The lowest level in the last 52 weeks (one year)." },
  pe: { meaning: "How many rupees you pay for every ₹1 of yearly profit. A higher number means the market expects more growth.",
        formula: "P/E = price ÷ profit per share" },
  pb: { meaning: "What you pay compared with the company's accounting net worth. Handy for banks and businesses with many assets.",
        formula: "P/B = price ÷ net worth per share" },
  dy: { meaning: "The cash dividend you get each year as a percent of the price. Like rent on your shares.",
        formula: "Yield % = yearly dividend ÷ price × 100" },
  ret: { meaning: "The simple price change over the last 252 trading sessions (about one year).",
         formula: "Return = (End ÷ Start − 1) × 100" },
};

const BENCH = [
  { slug: "nifty-50", label: "NIFTY 50" },
  { slug: "sensex", label: "SENSEX" },
  { slug: "bank-nifty", label: "BANK NIFTY" },
  { slug: "nifty-it", label: "NIFTY IT" },
  { slug: "india-vix", label: "INDIA VIX" },
];

function RangeBar({ last, low, high, tone = "accent" }: { last?: number | null; low?: number | null; high?: number | null; tone?: string }) {
  if (last == null || low == null || high == null || high <= low) {
    return <div className="h-1.5 rounded-full" style={{ background: "var(--line)" }} />;
  }
  const p = Math.max(0, Math.min(100, ((last - low) / (high - low)) * 100));
  return (
    <div className="relative h-1.5 rounded-full" style={{ background: "var(--line)" }}>
      <div className="absolute inset-y-0 left-0 rounded-full"
           style={{ width: `${p}%`, background: `var(--${tone})`, opacity: 0.55 }} />
      <div className="absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full"
           style={{ left: `calc(${p}% - 5px)`, background: `var(--${tone})`,
                    boxShadow: `0 0 0 2px var(--surface), 0 0 10px var(--${tone})` }} />
    </div>
  );
}

function envVal<T = number>(e?: Env<T>): T | null {
  return e && e.value != null ? e.value : null;
}

export default function Home() {
  const [idx, setIdx] = useState<Idx[] | null>(null);
  const [pulse, setPulse] = useState<any>(null);
  const [counts, setCounts] = useState<Counts | null>(null);
  const [active, setActive] = useState("nifty-50");
  const [detail, setDetail] = useState<Record<string, any>>({});
  const [intraday, setIntraday] = useState<Record<string, any>>({});

  useEffect(() => {
    getJSON<{ indices: Idx[] }>("/indices?expand=true").then((r) => setIdx(r.indices)).catch(() => setIdx([]));
    getJSON("/pulse").then(setPulse).catch(() => {});
    getJSON<Counts>("/meta/counts").then(setCounts).catch(() => {});
  }, []);

  useEffect(() => {
    if (!detail[active]) {
      getJSON(`/indices/${active}`)
        .then((r) => setDetail((d) => ({ ...d, [active]: r })))
        .catch(() => {});
    }
    if (!intraday[active]) {
      getJSON(`/indices/${active}/intraday`)
        .then((r) => setIntraday((m) => ({ ...m, [active]: r })))
        .catch(() => {});
    }
  }, [active, detail, intraday]);

  const bySlug = useMemo(() => {
    const m: Record<string, Idx> = {};
    (idx || []).forEach((i) => { m[i.slug] = i; });
    return m;
  }, [idx]);

  const nifty = bySlug["nifty-50"];
  const vix = bySlug["india-vix"];
  const breadth = pulse?.breadth;
  const d = detail[active];
  const chartIdx = bySlug[active];
  const intra = intraday[active];
  const intradayPoints = useMemo(
    () => (intra?.points || []).map((p: any) => ({
      date: p.date, close: p.c, open: p.o, high: p.h, low: p.l,
      time: p.time, datetime: p.datetime, volume: p.v,
    })),
    [intra],
  );

  const desks = [
    { t: "Indices", href: "/indices", icon: "Σ", b: "Benchmarks, sectorals and India VIX with 5Y history.", m: counts ? `${counts.indices} indices · ${counts.constituents} constituents` : "—" },
    { t: "Equities", href: "/stocks", icon: "◆", b: "Deep-dive fundamentals, DCF, peers and F&O.", m: counts ? `${counts.equities} companies` : "—" },
    { t: "IPO", href: "/ipos", icon: "↑", b: "Mainboard and SME issues with honest source status.", m: counts ? `${counts.ipos} issues tracked` : "—" },
    { t: "Mutual Funds", href: "/mutual-funds", icon: "◉", b: "Every AMFI scheme, NAV series, SIP and SWP math.", m: counts ? `${counts.funds.toLocaleString("en-IN")} schemes` : "—" },
    { t: "ETFs", href: "/etfs", icon: "▤", b: "Exchange-traded funds with iNAV context.", m: counts ? `${counts.etfs} ETFs` : "—" },
    { t: "Bonds & Debt", href: "/bonds", icon: "▬", b: "G-Sec structure, coupon math and YTM solver.", m: counts ? `${counts.bonds} G-Secs` : "—" },
    { t: "Gold & Silver", href: "/gold-silver", icon: "✦", b: "International spot, ₹ conversion and per-gram math.", m: counts ? `${counts.commodities} metals` : "—" },
    { t: "Corporate Events", href: "/events", icon: "▦", b: "Dividends, splits and board meetings — the real calendar.", m: counts ? `${counts.events} actions` : "—" },
    { t: "REITs", href: "/reits", icon: "▮", b: "Trust units with the 90% NDCA rule explained.", m: counts ? `${counts.reits} trusts` : "—" },
    { t: "Market Pulse", href: "/market-pulse", icon: "≋", b: "The 4 PM end-of-day x-ray: breadth, flows, actions.", m: breadth ? `${breadth.advances}A / ${breadth.declines}D` : "—" },
    { t: "AI Quant", href: "/ai-quant-hub", icon: "⌁", b: "RangeCast bands, StreetPulse flow and EOD x-ray.", m: "Model engines" },
    { t: "Academy", href: "/learn", icon: "◇", b: "Beginner-to-derivatives course — free and structured.", m: "Free tracks" },
  ];

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6">
      {/* ---------------- HERO ---------------- */}
      <section className="relative -mx-4 sm:-mx-6 px-4 sm:px-6 pt-10 pb-10 overflow-hidden">
        <div className="hero-grid" aria-hidden />
        <div className="relative grid lg:grid-cols-[1.3fr_.7fr] gap-8 items-end">
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-5">
              <span className="chip chip-live !text-[9.5px]">
                <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-[var(--up)] inline-block" />
                Live market terminal
              </span>
              <span className="chip !text-[9.5px]">Facts · Math · Education</span>
              <span className="chip !text-[9.5px]">No tips · No calls</span>
            </div>
            <h1 className="text-[38px] sm:text-[56px] lg:text-[62px] font-black leading-[0.97] tracking-tight">
              India’s capital markets,
              <br />
              <span style={{ color: "var(--accent)" }}>decoded to the last basis point.</span>
            </h1>
            <p className="muted text-[14.5px] leading-relaxed mt-5 max-w-2xl">
              Every index, stock, option chain, fund, bond and trust — with five-year
              depth, our own Black-Scholes and DCF engines, statutory-charge
              transparency and zero-KYC paper trading. Computed locally from free
              public exchange data.{" "}
              <strong style={{ color: "var(--ink)" }}>Not a buy or sell recommendation.</strong>
            </p>
            <div className="flex flex-wrap gap-2.5 mt-7">
              <Link href="/indices" className="btn-primary">Explore indices →</Link>
              <Link href="/stocks" className="btn-secondary">Open equity screener</Link>
              <Link href="/ai-quant-hub" className="btn-secondary">AI Quant Hub</Link>
            </div>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 mt-6 muted text-[11px]">
              <span><b style={{ color: "var(--ink)" }}>{counts?.indices ?? "—"}</b> indices</span>
              <span className="opacity-30">·</span>
              <span><b style={{ color: "var(--ink)" }}>{counts?.equities ?? "—"}</b> equities</span>
              <span className="opacity-30">·</span>
              <span><b style={{ color: "var(--ink)" }}>{counts ? counts.funds.toLocaleString("en-IN") : "—"}</b> funds</span>
              <span className="opacity-30">·</span>
              <span><b style={{ color: "var(--ink)" }}>5Y</b> OHLCV depth</span>
            </div>
          </div>

          {/* market snapshot card */}
          <div className="card p-4 sm:p-5 relative overflow-hidden">
            <div className="absolute inset-x-0 top-0 h-px"
                 style={{ background: "linear-gradient(90deg, transparent, var(--accent), transparent)", opacity: 0.6 }} />
            <div className="flex items-center justify-between gap-3 mb-4">
              <div>
                <div className="muted text-[10px] font-bold uppercase tracking-[0.16em]">Market snapshot</div>
                <div className="text-[13px] font-bold mt-0.5">NSE · BSE · GIFT corridor</div>
              </div>
              <MarketClock showSeconds />
            </div>
            {nifty ? (
              <>
                <div className="flex items-end justify-between gap-3">
                  <div>
                    <div className="muted text-[11px] font-semibold">NIFTY 50</div>
                    <div className="knum text-[30px] font-black leading-none mt-1">
                      {inr(envVal(nifty.last))}
                    </div>
                  </div>
                  <div className={`knum text-[16px] font-black ${(envVal(nifty.changepct) || 0) >= 0 ? "text-up" : "text-down"}`}>
                    {pct(envVal(nifty.changepct))}
                  </div>
                </div>
                <div className="mt-4">
                  <div className="flex justify-between muted text-[10px] mb-1.5">
                    <span>{inr(nifty.year_range?.value?.[0])}</span>
                    <span>
                      <MetricTip label="52W range" tip={{
                        meaning: "The lowest and highest NIFTY 50 level over the last 52 weeks. The bar shows where today sits inside that range.",
                        formula: "Position % = (Last − 52W low) ÷ (52W high − 52W low) × 100",
                      }}>52W range</MetricTip>
                    </span>
                    <span>{inr(nifty.year_range?.value?.[1])}</span>
                  </div>
                  <RangeBar last={envVal(nifty.last)} low={nifty.year_range?.value?.[0]} high={nifty.year_range?.value?.[1]}
                            tone={(envVal(nifty.changepct) || 0) >= 0 ? "up" : "down"} />
                </div>
                <div className="grid grid-cols-3 gap-2 mt-4 pt-4" style={{ borderTop: "1px solid var(--line)" }}>
                  <div>
                    <div className="muted text-[9.5px] font-bold uppercase tracking-wider">
                      <MetricTip label="Advances" tip={{
                        meaning: "Number of tracked stocks that closed higher than their previous close today.",
                      }}>Advances</MetricTip>
                    </div>
                    <div className="knum text-[15px] font-bold text-up">{breadth?.advances ?? "—"}</div>
                  </div>
                  <div>
                    <div className="muted text-[9.5px] font-bold uppercase tracking-wider">
                      <MetricTip label="Declines" tip={{
                        meaning: "Number of tracked stocks that closed lower than their previous close today.",
                      }}>Declines</MetricTip>
                    </div>
                    <div className="knum text-[15px] font-bold text-down">{breadth?.declines ?? "—"}</div>
                  </div>
                  <div>
                    <div className="muted text-[9.5px] font-bold uppercase tracking-wider">
                      <MetricTip label="India VIX" tip={{
                        meaning: "The NSE's implied-volatility index from NIFTY options: the market's priced expectation of near-term movement.",
                        example: "15.65 implies roughly a 15.65% annualised move; it says nothing about direction.",
                      }}>India VIX</MetricTip>
                    </div>
                    <div className="knum text-[15px] font-bold">{vix ? inr(envVal(vix.last)) : "—"}</div>
                  </div>
                </div>
              </>
            ) : (
              <div className="skeleton h-[150px]" />
            )}
          </div>
        </div>
      </section>

      {/* ---------------- LIVE PULSE STRIP ---------------- */}
      <section className="pb-10">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--up)] animate-pulseSoft inline-block" />
            <h2 className="text-[13px] font-extrabold tracking-tight uppercase tracking-[0.12em]">Market pulse</h2>
          </div>
          <Link href="/indices" className="text-[11.5px] accent font-semibold hover:underline">All 18 indices →</Link>
        </div>
        <div className="flex gap-2.5 overflow-x-auto scrollbar-none pb-1">
          {(idx || []).filter((i) => BENCH.some((b) => b.slug === i.slug)).map((i) => {
            const up = (envVal(i.changepct) || 0) >= 0;
            const lo = i.year_range?.value?.[0], hi = i.year_range?.value?.[1];
            return (
              <Link key={i.slug} href={`/indices/${i.slug}`}
                    className="card card-hover p-3.5 min-w-[196px] flex-1 max-w-[280px]">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11.5px] font-bold truncate">{i.name}</span>
                  <span className="chip !text-[8.5px] !py-0.5">{i.group || "Index"}</span>
                </div>
                <div className="flex items-baseline justify-between gap-2 mt-2">
                  <span className="knum text-[17px] font-black">{inr(envVal(i.last))}</span>
                  <span className={`knum text-[11.5px] font-bold ${up ? "text-up" : "text-down"}`}>{pct(envVal(i.changepct))}</span>
                </div>
                <div className="mt-2.5"><RangeBar last={envVal(i.last)} low={lo} high={hi} tone={up ? "up" : "down"} /></div>
                <div className="flex justify-between muted text-[9.5px] mt-1.5">
                  <span>{inr(lo)}</span><span>52W</span><span>{inr(hi)}</span>
                </div>
              </Link>
            );
          })}
          {!idx && Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton h-[112px] min-w-[196px] flex-1" />)}
        </div>
      </section>

      {/* ---------------- MAIN INTERACTIVE CHART ---------------- */}
      <section className="pb-12">
        <SectionTitle
          title="Benchmark intelligence"
          sub="Switch the main chart across the five benchmarks. Hover for the exact date, price and period change."
          right={<Link href={`/indices/${active}`} className="btn-secondary !px-3 !py-1.5 !text-[12px]">Open {chartIdx?.name || "index"} desk →</Link>}
        />
        <div className="card p-4 sm:p-5">
          <div className="flex flex-wrap items-center gap-1.5 mb-4">
            {BENCH.map((b) => (
              <button key={b.slug} onClick={() => setActive(b.slug)}
                      className={`rounded-md px-3 py-1.5 text-[12px] font-semibold transition-colors ${active === b.slug ? "text-white" : "muted hover:text-[var(--ink)]"}`}
                      style={active === b.slug ? { background: "var(--accent)", color: "#041018" } : { border: "1px solid var(--line)" }}>
                {b.label}
              </button>
            ))}
            <span className="ml-auto muted text-[10.5px]">
              {chartIdx?.asof
                ? `Session ${fmtDate(chartIdx.asof)}`
                : "Free delayed feed"}
            </span>
          </div>

          <div className="grid lg:grid-cols-[1fr_286px] gap-5">
            <div>
              {d ? (
                <LineChart points={d.history || []} height={320} defaultRange="1D"
                           intradayPoints={intradayPoints}
                           intradaySource={intra?.source}
                           prevClose={envVal(d.prev_close)}
                           title={`${d.name} · price history`} />
              ) : (
                <div className="skeleton h-[340px]" />
              )}
            </div>
            <aside className="space-y-2.5">
              <div className="rounded-lg p-3.5" style={{ background: "var(--surface-2)", border: "1px solid var(--line)" }}>
                <div className="muted text-[9.5px] font-bold uppercase tracking-[0.14em]">Last close</div>
                <div className="knum text-[26px] font-black mt-1">{d ? inr(envVal(d.last)) : "—"}</div>
                <div className={`knum text-[13px] font-bold mt-0.5 ${(envVal(d?.changepct) || 0) >= 0 ? "text-up" : "text-down"}`}>
                  {d ? pct(envVal(d.changepct)) : "—"} <span className="muted font-normal text-[10.5px]">today</span>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {([
                  { k: "Open", v: d ? inr(envVal(d.open)) : "—", tip: HTIPS.open },
                  { k: "Prev close", v: d ? inr(envVal(d.prev_close)) : "—", tip: HTIPS.prev },
                  { k: "52W high", v: d ? inr(envVal(d.high_52w)) : "—", tip: HTIPS.high },
                  { k: "52W low", v: d ? inr(envVal(d.low_52w)) : "—", tip: HTIPS.low },
                  { k: "P/E", v: d ? (envVal(d.pe) ?? "—") : "—", tip: HTIPS.pe },
                  { k: "P/B", v: d ? (envVal(d.pb) ?? "—") : "—", tip: HTIPS.pb },
                  { k: "Div yield", v: d ? (envVal(d.dy) != null ? `${envVal(d.dy)}%` : "—") : "—", tip: HTIPS.dy },
                  { k: "1Y return", v: d ? pct(envVal(d.returns?.["1y"])) : "—", tip: HTIPS.ret },
                ]).map(({ k, v, tip }) => (
                  <div key={k} className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
                    <div className="muted text-[9px] font-bold uppercase tracking-wider">
                      <MetricTip label={k} tip={tip}>{k}</MetricTip>
                    </div>
                    <div className="knum text-[12.5px] font-bold mt-0.5">{v}</div>
                  </div>
                ))}
              </div>
              <Link href={`/indices/${active}`} className="btn-secondary w-full !py-2 !text-[12px]">
                Full performance & constituents →
              </Link>
            </aside>
          </div>
        </div>
      </section>

      {/* ---------------- MOVERS ---------------- */}
      <section className="pb-12">
        <div className="grid lg:grid-cols-2 gap-4">
          {[
            { key: "top_gainers", title: "Top gainers", tone: "up", rows: pulse?.top_gainers || [] },
            { key: "top_losers", title: "Top losers", tone: "down", rows: pulse?.top_losers || [] },
          ].map((block) => (
            <div key={block.key} className="card overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "1px solid var(--line)" }}>
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full" style={{ background: `var(--${block.tone})` }} />
                  <h3 className="text-[13px] font-extrabold">{block.title}</h3>
                </div>
                <Link href="/market-pulse" className="text-[11px] accent font-semibold hover:underline">full pulse →</Link>
              </div>
              <div className="grid grid-cols-[1.4fr_.7fr_.6fr] gap-2 px-4 py-2 table-head">
                <span>Company</span><span className="text-right">Last</span><span className="text-right">Day</span>
              </div>
              {block.rows.slice(0, 6).map((m: any, i: number) => (
                <Link key={block.key + m.symbol + i} href={m.href}
                      className="table-row grid grid-cols-[1.4fr_.7fr_.6fr] gap-2 px-4 py-2.5 items-center">
                  <span className="min-w-0">
                    <span className="block text-[12.5px] font-bold truncate">{m.symbol}</span>
                    <span className="block muted text-[10.5px] truncate">{m.name}</span>
                  </span>
                  <span className="knum text-[12.5px] text-right font-semibold">{inr(m.last)}</span>
                  <span className={`knum text-[12px] text-right font-bold ${(m.changepct || 0) >= 0 ? "text-up" : "text-down"}`}>{pct(m.changepct)}</span>
                </Link>
              ))}
              {!block.rows.length && (
                <div className="px-4 py-8 text-center muted text-[12px]">
                  Movers populate after the equity seed/refresh completes.
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* ---------------- SECTOR HEATMAP ---------------- */}
      <section className="pb-12">
        <SectionTitle
          title="Sectoral heatmap"
          sub="Average day change across the tracked equity universe, grouped by NSE sector."
          right={<Link href="/market-pulse" className="text-[11.5px] accent font-semibold hover:underline">Open market pulse →</Link>}
        />
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
          {(pulse?.sector_flows || []).slice(0, 10).map((s: any) => {
            const up = (s.avg_change || 0) >= 0;
            const strength = Math.min(Math.abs(s.avg_change || 0) / 2.5, 1);
            return (
              <div key={s.sector} className="rounded-lg p-3.5"
                   style={{
                     border: `1px solid color-mix(in srgb, var(--${up ? "up" : "down"}) ${25 + strength * 30}%, var(--line))`,
                     background: `color-mix(in srgb, var(--${up ? "up" : "down"}) ${6 + strength * 14}%, var(--surface))`,
                   }}>
                <div className="text-[11.5px] font-bold leading-tight line-clamp-2 min-h-[28px]">{s.sector}</div>
                <div className={`knum text-[17px] font-black mt-1 ${up ? "text-up" : "text-down"}`}>{pct(s.avg_change)}</div>
                <div className="muted text-[9.5px] mt-1">{s.advance}A / {s.decline}D</div>
              </div>
            );
          })}
          {!pulse?.sector_flows?.length && Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton h-[92px]" />)}
        </div>
      </section>

      {/* ---------------- DESKS ---------------- */}
      <section className="pb-16">
        <SectionTitle
          title="The twelve desks"
          sub="One terminal, every Indian capital-markets desk — each with live row counts from the local store."
        />
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {desks.map((c) => (
            <Link key={c.href} href={c.href} className="card card-hover p-4 block group">
              <div className="flex items-start justify-between gap-2">
                <span className="grid h-8 w-8 place-items-center rounded-md text-[15px] font-black"
                      style={{ background: "color-mix(in srgb, var(--accent) 10%, var(--surface-2))",
                               border: "1px solid color-mix(in srgb, var(--accent) 25%, var(--line))",
                               color: "var(--accent)" }}>
                  {c.icon}
                </span>
                <span className="text-[11px] accent opacity-0 group-hover:opacity-100 transition-opacity">→</span>
              </div>
              <div className="text-[13.5px] font-bold mt-2.5">{c.t}</div>
              <p className="muted text-[11.5px] mt-1 leading-relaxed min-h-[34px]">{c.b}</p>
              <div className="mt-2.5 pt-2.5 flex items-center justify-between gap-2" style={{ borderTop: "1px solid var(--line-soft)" }}>
                <span className="knum text-[10.5px] font-semibold accent">{c.m}</span>
                <span className="muted text-[9.5px] uppercase tracking-wider">open</span>
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* ---------------- DATA INTEGRITY ---------------- */}
      <section className="pb-16">
        <div className="card p-5 grid md:grid-cols-3 gap-5">
          {[
            { t: "Markets it covers", b: "NSE and BSE listed companies, benchmark and sectoral indices, NIFTY/BANK NIFTY/SENSEX derivatives, mainboard and SME IPOs, mutual funds, ETFs, government bonds, gold and silver, and REIT/InvIT trusts." },
            { t: "How it computes", b: "Free public feeds deliver only raw ingredients. Every P/E, CAGR, DCF value, option Greek, probabilistic band and statutory charge is calculated by our own Python engine (NumPy/SciPy) — nothing is borrowed blindly." },
            { t: "What it is — and is not", b: "A factual database and education tool. Numbers carry their status: if data is not listed, not applicable to a sector, or not disclosed, the platform says exactly that — never a silent blank and never a fabricated fill." },
          ].map((c) => (
            <div key={c.t}>
              <div className="text-[13px] font-bold mb-1.5">{c.t}</div>
              <p className="muted text-[11.5px] leading-relaxed">{c.b}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
