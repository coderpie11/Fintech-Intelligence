"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getJSON, postJSON, type Env } from "@/lib/api";
import { fmtDate, inr, pct } from "@/lib/format";
import {
  ErrorBox, PageHeader, RefreshButton, SectionTitle, Skeleton, StatGrid,
} from "@/components/PageKit";
import MetricTip, { type Tip } from "@/components/MetricTip";
import LineChart from "@/components/LineChart";

type EtfRow = {
  symbol: string;
  name: string;
  category?: string;
  issuer?: string;
  about?: string;
  ltp: Env;
  changepct: Env;
  nav: Env;
  premium_discount_pct: Env;
  open: Env;
  high: Env;
  low: Env;
  week52_high: Env;
  week52_low: Env;
  volume: Env;
  turnover_cr: Env;
  impact_cost_pct: Env;
  tracking_error_pct?: Env;
  liquidity_score: Env;
  returns: Record<string, Env>;
  benchmark?: string;
  has_history: boolean;
  href: string;
  quote_source?: string;
};

const TIPS: Record<string, Tip> = {
  premium: {
    meaning:
      "Premium / Discount to NAV: how far the exchange price sits above or below the fund's published net asset value. A positive number means the ETF trades richer than its underlying assets.",
    formula: "Premium % = (Market price − NAV) ÷ NAV × 100",
    example: "Price ₹113.20 against NAV ₹115.02 is a 1.59% discount.",
  },
  te: {
    meaning:
      "Tracking Error: the annualised volatility of the gap between the ETF's returns and its benchmark's returns. Lower means the ETF follows its index more tightly.",
    formula: "TE = standard deviation(ETF return − Benchmark return) × √252",
    example: "A 0.6% tracking error is tight; 2%+ deserves a closer look at liquidity and fees.",
  },
  impact: {
    meaning:
      "Impact Cost: the modelled price concession for executing an order, proxied from the day's range and traded quantity. It is not an order-book measurement.",
    formula: "Impact ≈ half the day's range ÷ √(quantity ÷ 1 lakh)",
    example: "A 0.08% impact cost means a ₹1 lakh buy pays about ₹80 in slippage.",
  },
  liquidity: {
    meaning:
      "Liquidity Score: a 0–100 platform score built from turnover and traded quantity. Higher means it is easier to enter and exit without moving the price.",
    formula: "Score = 18·log10(turnover ₹Cr + 1) + 10·log10(volume ÷ 1 lakh + 1) + 18",
    example: "A score above 75 indicates a deep, actively traded ETF.",
  },
  cagr: {
    meaning:
      "Compound Annual Growth Rate: the smooth yearly rate that takes the starting price to today's price.",
    formula: "CAGR = (End ÷ Start)^(1 ÷ Years) − 1",
    example: "₹100 → ₹161 over 5 years is a 10% CAGR.",
  },
};

function envNum(e?: Env): number | null {
  return e && e.value != null ? e.value : null;
}

function PctCell({ env, strong = false, active = false }: { env?: Env; strong?: boolean; active?: boolean }) {
  const v = envNum(env);
  return (
    <span className={`knum text-[11.5px] ${strong || active ? "font-bold" : ""} ${v == null ? "muted" : v >= 0 ? "text-up" : "text-down"}`}>
      {v != null ? pct(v) : "—"}
    </span>
  );
}

const ETF_TYPES = [
  "All ETFs", "Silver ETFs", "Gold ETFs", "Nifty 50 & Broad Index",
  "Sensex ETFs", "Midcap & Next 50", "Banking & Financial",
  "IT & Sectoral", "International / Nasdaq", "PSU & CPSE", "Liquid & Debt",
];

const PERIODS = [
  { key: "1m", label: "1 Month (1M)" },
  { key: "3m", label: "3 Months (3M)" },
  { key: "6m", label: "6 Months (6M)" },
  { key: "1y", label: "1 Year (1Y)" },
  { key: "3y", label: "3 Years (3Y CAGR)" },
  { key: "5y", label: "5 Years (5Y CAGR)" },
] as const;

type PeriodKey = (typeof PERIODS)[number]["key"];

function etfBucket(e: EtfRow): string {
  const cat = (e.category || "").toLowerCase();
  const hay = `${cat} ${(e.name || "").toLowerCase()}`;
  if (cat === "silver" || /silver/.test(hay)) return "Silver ETFs";
  if (cat === "gold" || /gold/.test(hay)) return "Gold ETFs";
  if (cat === "sensex" || /sensex/.test(hay)) return "Sensex ETFs";
  if (cat === "mid & next 50" || /midcap|mid cap|next 50/.test(hay)) return "Midcap & Next 50";
  if (cat === "banking" || /bank|financial/.test(hay)) return "Banking & Financial";
  if (cat === "international" || /nasdaq|international|hang seng|fang/.test(hay)) return "International / Nasdaq";
  if (cat === "psu" || /psu|cpse|bharat/.test(hay)) return "PSU & CPSE";
  if (cat === "liquid & debt" || /liquid|debt|gilt|sdl/.test(hay)) return "Liquid & Debt";
  if (cat === "it & sectoral" || /sectoral|pharma|auto|infra|consum|information technology|\bit\b/.test(hay)) return "IT & Sectoral";
  return "Nifty 50 & Broad Index";
}

export function EtfList() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [type, setType] = useState("All ETFs");
  const [period, setPeriod] = useState<PeriodKey>("1y");
  const [order, setOrder] = useState<"desc" | "asc">("desc");

  useEffect(() => {
    setErr(null);
    getJSON("/etfs").then(setData).catch((e) => setErr(String(e.message || e)));
  }, []);

  const rows = useMemo(() => {
    const list: EtfRow[] = data?.etfs || [];
    const needle = q.trim().toLowerCase();
    const filtered = list.filter((e) => {
      if (type !== "All ETFs" && etfBucket(e) !== type) return false;
      if (!needle) return true;
      return e.symbol.toLowerCase().includes(needle)
        || e.name.toLowerCase().includes(needle)
        || (e.category || "").toLowerCase().includes(needle);
    });
    return [...filtered].sort((a, b) => {
      const av = envNum(a.returns?.[period]);
      const bv = envNum(b.returns?.[period]);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return order === "desc" ? bv - av : av - bv;
    });
  }, [data, q, type, period, order]);

  const stats = useMemo(() => {
    const list: EtfRow[] = data?.etfs || [];
    const turnover = list.map((e) => envNum(e.turnover_cr) || 0);
    const premiums = list.map((e) => envNum(e.premium_discount_pct)).filter((v): v is number => v != null);
    const avgPrem = premiums.length ? premiums.reduce((a, b) => a + b, 0) / premiums.length : null;
    const top = [...list].sort((a, b) => (envNum(b.turnover_cr) || 0) - (envNum(a.turnover_cr) || 0))[0];
    return {
      count: list.length,
      turnover: turnover.reduce((a, b) => a + b, 0),
      avgPrem,
      top,
    };
  }, [data]);

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6">
      <PageHeader
        eyebrow="Exchange-traded funds"
        title="ETF Desk"
        sub="Curated NSE-listed ETFs with live quotes, five-year price history, premium/discount to published NAV, tracking error, impact cost and liquidity scoring."
        right={<RefreshButton stage="etfs" />}
      />

      {err && <ErrorBox message={err} stage="etfs" />}
      {!data && !err && <Skeleton rows={8} />}

      {data && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 mb-4">
            <div className="card p-3">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">ETFs covered</div>
              <div className="knum text-[20px] font-black mt-1">{stats.count}</div>
              <div className="muted text-[10px] mt-0.5">curated NSE universe</div>
            </div>
            <div className="card p-3">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Combined turnover</div>
              <div className="knum text-[20px] font-black mt-1">₹{stats.turnover.toLocaleString("en-IN")} Cr</div>
              <div className="muted text-[10px] mt-0.5">latest session</div>
            </div>
            <div className="card p-3">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Average premium / discount</div>
              <div className={`knum text-[20px] font-black mt-1 ${(stats.avgPrem || 0) >= 0 ? "text-up" : "text-down"}`}>
                {stats.avgPrem != null ? pct(stats.avgPrem) : "—"}
              </div>
              <div className="muted text-[10px] mt-0.5">versus latest published NAV</div>
            </div>
            <div className="card p-3">
              <div className="muted text-[9.5px] font-bold uppercase tracking-[0.13em]">Most traded</div>
              <div className="knum text-[17px] font-black mt-1">{stats.top?.symbol || "—"}</div>
              <div className="muted text-[10px] mt-0.5">{stats.top?.name?.slice(0, 34) || "—"}</div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 mb-3">
            <div className="surface rounded-lg px-3 py-1.5 flex-1 min-w-[220px] max-w-md">
              <input value={q} onChange={(e) => setQ(e.target.value)}
                     placeholder="Search ETF, symbol or category…"
                     className="w-full bg-transparent text-[12.5px] outline-none"
                     style={{ color: "var(--ink)" }} />
            </div>
            <label className="flex items-center gap-1.5">
              <span className="muted text-[9.5px] font-bold uppercase tracking-[0.12em]">Type</span>
              <select value={type} onChange={(e) => setType(e.target.value)}
                      className="surface rounded-lg px-2.5 py-1.5 text-[12px]" style={{ color: "var(--ink)" }}>
                {ETF_TYPES.map((t) => <option key={t}>{t}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-1.5">
              <span className="muted text-[9.5px] font-bold uppercase tracking-[0.12em]">Return period</span>
              <select value={period} onChange={(e) => setPeriod(e.target.value as PeriodKey)}
                      className="surface rounded-lg px-2.5 py-1.5 text-[12px]" style={{ color: "var(--ink)" }}>
                {PERIODS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-1.5">
              <span className="muted text-[9.5px] font-bold uppercase tracking-[0.12em]">Sort by return</span>
              <select value={order} onChange={(e) => setOrder(e.target.value as "desc" | "asc")}
                      className="surface rounded-lg px-2.5 py-1.5 text-[12px]" style={{ color: "var(--ink)" }}>
                <option value="desc">Highest Return First (Max → Min ↓)</option>
                <option value="asc">Lowest Return First (Min → Max ↑)</option>
              </select>
            </label>
            <span className="chip !text-[9.5px]">{data.quote_feed}</span>
            <span className="muted text-[11px]">{rows.length} shown</span>
          </div>

          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1380px] border-collapse">
                <thead>
                  <tr style={{ background: "var(--surface-2)" }}>
                    <th className="table-head text-left px-3 py-2.5">ETF</th>
                    <th className="table-head text-left px-2.5 py-2.5">Category</th>
                    <th className="table-head text-right px-2.5 py-2.5">LTP</th>
                    <th className="table-head text-right px-2.5 py-2.5">Day</th>
                    <th className="table-head text-right px-2.5 py-2.5">
                      <MetricTip label="NAV" tip={{ meaning: "Net asset value per unit: the value of the fund's underlying holdings divided by units outstanding, published once a day." }}>NAV</MetricTip>
                    </th>
                    <th className="table-head text-right px-2.5 py-2.5">
                      <MetricTip label="Prem / Disc" tip={TIPS.premium}>Prem / Disc</MetricTip>
                    </th>
                    {PERIODS.map((p) => (
                      <th key={p.key} className="table-head text-right px-2.5 py-2.5"
                          style={period === p.key ? { color: "var(--accent)" } : undefined}>
                        {p.key.toUpperCase()}{p.key === "3y" || p.key === "5y" ? " CAGR" : ""}
                      </th>
                    ))}
                    <th className="table-head text-right px-2.5 py-2.5">Turnover</th>
                    <th className="table-head text-right px-2.5 py-2.5">
                      <MetricTip label="Impact" tip={TIPS.impact}>Impact</MetricTip>
                    </th>
                    <th className="table-head text-right px-2.5 py-2.5">
                      <MetricTip label="Tracking err." tip={TIPS.te}>Tracking err.</MetricTip>
                    </th>
                    <th className="table-head text-right px-3 py-2.5">
                      <MetricTip label="Liquidity" tip={TIPS.liquidity}>Liquidity</MetricTip>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((e) => (
                    <tr key={e.symbol} className="table-row">
                      <td className="px-3 py-2.5 min-w-[230px]">
                        <Link href={e.href} className="text-[12.5px] font-bold hover:underline">{e.symbol}</Link>
                        <div className="muted text-[10.5px] truncate max-w-[260px]">{e.name}</div>
                      </td>
                      <td className="px-2.5 py-2.5 muted text-[11px]">{e.category || "—"}</td>
                      <td className="px-2.5 py-2.5 text-right knum text-[12px] font-semibold">{envNum(e.ltp) != null ? inr(envNum(e.ltp)) : "—"}</td>
                      <td className="px-2.5 py-2.5 text-right"><PctCell env={e.changepct} /></td>
                      <td className="px-2.5 py-2.5 text-right knum text-[11.5px]">{envNum(e.nav) != null ? inr(envNum(e.nav)) : "—"}</td>
                      <td className={`px-2.5 py-2.5 text-right knum text-[11.5px] font-semibold ${(envNum(e.premium_discount_pct) || 0) >= 0 ? "text-up" : "text-down"}`}>
                        {envNum(e.premium_discount_pct) != null ? pct(envNum(e.premium_discount_pct)) : "—"}
                      </td>
                      {PERIODS.map((p) => (
                        <td key={p.key} className="px-2.5 py-2.5 text-right"
                            style={period === p.key ? { background: "color-mix(in srgb, var(--accent) 7%, transparent)" } : undefined}>
                          <PctCell env={e.returns?.[p.key]}
                                   strong={p.key === "3y" || p.key === "5y"}
                                   active={period === p.key} />
                        </td>
                      ))}
                      <td className="px-2.5 py-2.5 text-right knum text-[11px]">
                        {envNum(e.turnover_cr) != null ? `₹${Number(envNum(e.turnover_cr)).toLocaleString("en-IN")} Cr` : "—"}
                      </td>
                      <td className="px-2.5 py-2.5 text-right knum text-[11px]">
                        {envNum(e.impact_cost_pct) != null ? `${Number(envNum(e.impact_cost_pct)).toFixed(3)}%` : "—"}
                      </td>
                      <td className="px-2.5 py-2.5 text-right knum text-[11px]">
                        {envNum(e.tracking_error_pct) != null ? `${Number(envNum(e.tracking_error_pct)).toFixed(2)}%` : "—"}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <span className="knum text-[11.5px] font-bold">{envNum(e.liquidity_score) ?? "—"}</span>
                        <div className="muted text-[9px]">/ 100</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="px-3.5 py-2.5 muted text-[10.5px] leading-relaxed flex flex-wrap gap-x-4 gap-y-1"
                 style={{ borderTop: "1px solid var(--line)", background: "var(--surface-2)" }}>
              <span>{data.universe_note}</span>
              <span className="opacity-40">·</span>
              <span>Premium/discount uses NSE's latest published NAV, not an intraday iNAV.</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export function EtfDetail({ symbol }: { symbol: string }) {
  const sym = (symbol || "").toUpperCase();
  const [d, setD] = useState<any>(null);
  const [intraday, setIntraday] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  const [amount, setAmount] = useState("100000");
  const [years, setYears] = useState("5");
  const [expected, setExpected] = useState("");
  const [etfTer, setEtfTer] = useState("0.20");
  const [mfTer, setMfTer] = useState("0.20");
  const [vs, setVs] = useState<any>(null);
  const [vsErr, setVsErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    setD(null);
    setIntraday(null);
    setErr(null);
    getJSON(`/etfs/${encodeURIComponent(sym)}`)
      .then((r) => {
        if (!live) return;
        setD(r);
        const e = r.calculator_defaults?.expected_return_pct;
        if (e != null) setExpected(String(Number(e).toFixed(2)));
        if (r.calculator_defaults?.etf_ter_pct != null) setEtfTer(String(r.calculator_defaults.etf_ter_pct));
        if (r.calculator_defaults?.index_fund_ter_pct != null) setMfTer(String(r.calculator_defaults.index_fund_ter_pct));
      })
      .catch((e) => { if (live) setErr(String(e.message || e)); });
    getJSON(`/etfs/${encodeURIComponent(sym)}/intraday`)
      .then((r) => { if (live) setIntraday(r); })
      .catch(() => {});
    return () => { live = false; };
  }, [sym]);

  const runVs = async () => {
    setBusy(true); setVsErr(null); setVs(null);
    try {
      const r = await postJSON(`/etfs/${encodeURIComponent(sym)}/vs-index-fund`, {
        amount: Number(amount) || 0,
        years: Number(years) || 1,
        expected_return_pct: expected === "" ? undefined : Number(expected),
        etf_ter_pct: Number(etfTer) || 0,
        index_fund_ter_pct: Number(mfTer) || 0,
      });
      setVs(r);
    } catch (e: any) {
      setVsErr(String(e.message || e).slice(0, 200));
    } finally {
      setBusy(false);
    }
  };

  if (err) {
    return (
      <div className="mx-auto max-w-[1600px] px-4 sm:px-6 py-8">
        <ErrorBox message={err} stage="etfs" />
        <Link href="/etfs" className="btn-secondary mt-4">← Back to ETFs</Link>
      </div>
    );
  }

  if (!d) {
    return (
      <div className="mx-auto max-w-[1600px] px-4 sm:px-6 py-8 space-y-3">
        <div className="skeleton h-16" />
        <Skeleton rows={7} />
      </div>
    );
  }

  const ltp = envNum(d.ltp);
  const chg = envNum(d.changepct);
  const nav = envNum(d.nav);
  const prem = envNum(d.premium_discount_pct);
  const te = envNum(d.tracking_error_pct);
  const points = (d.history || []).map((h: any) => ({
    date: h.date, close: h.close, open: h.open, high: h.high, low: h.low,
  }));
  const intradayPoints = (intraday?.points || []).map((p: any) => ({
    date: p.date, close: p.c, open: p.o, high: p.h, low: p.l,
    time: p.time, datetime: p.datetime, volume: p.v,
  }));

  return (
    <div className="mx-auto max-w-[1600px] px-4 sm:px-6 pb-16">
      <div className="pt-5 flex items-center gap-2 muted text-[11.5px]">
        <Link href="/etfs" className="hover:underline">ETFs</Link>
        <span className="opacity-40">/</span>
        <span style={{ color: "var(--ink)" }} className="font-semibold">{d.symbol}</span>
      </div>

      <PageHeader
        eyebrow={`${d.category || "ETF"}${d.issuer ? ` · ${d.issuer}` : ""} · ${d.symbol}`}
        title={d.name}
        sub={d.about}
        right={<RefreshButton stage="etfs" label="Refresh ETFs" />}
      />

      <div className="grid lg:grid-cols-[1fr_330px] gap-3 mb-4">
        <div className="card p-4 sm:p-5">
          <div className="flex flex-wrap items-end justify-between gap-3 mb-2">
            <div>
              <div className="muted text-[10px] font-bold uppercase tracking-[0.16em]">Last traded price</div>
              <div className="flex items-end gap-3 mt-1">
                <span className="knum text-[34px] font-black leading-none">{inr(ltp)}</span>
                <span className={`knum text-[15px] font-bold ${(chg || 0) >= 0 ? "text-up" : "text-down"}`}>{pct(chg)}</span>
              </div>
              <div className="muted text-[11px] mt-1.5">
                {d.quote_source} · NAV {nav != null ? inr(nav) : "—"} ·{" "}
                {prem != null ? `${prem >= 0 ? "premium" : "discount"} ${Math.abs(prem).toFixed(2)}%` : "premium n/a"}
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <span className={`chip !text-[9.5px] ${prem != null && prem >= 0 ? "chip-live" : ""}`}>
                {prem != null ? `${prem >= 0 ? "+" : ""}${prem.toFixed(2)}% vs NAV` : "NAV pending"}
              </span>
              {te != null && <span className="chip !text-[9.5px]">TE {te.toFixed(2)}%</span>}
              {envNum(d.liquidity_score) != null && <span className="chip !text-[9.5px]">Liquidity {envNum(d.liquidity_score)}/100</span>}
            </div>
          </div>

          <LineChart points={points} height={330} defaultRange="1D"
                     intradayPoints={intradayPoints}
                     intradaySource={intraday?.source}
                     prevClose={intraday?.prevClose ?? envNum(d.prev_close)}
                     title={`${d.symbol} · price history`} />
        </div>

        <aside className="card p-4 sm:p-5 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            {[
              ["Open", d.open, inr],
              ["Prev close", d.prev_close, inr],
              ["Day high", d.high, inr],
              ["Day low", d.low, inr],
              ["52W high", d.week52_high, inr],
              ["52W low", d.week52_low, inr],
            ].map(([label, env, fmt]: any) => (
              <div key={label} className="rounded-md px-2.5 py-2"
                   style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                <div className="muted text-[9px] font-bold uppercase tracking-wider">{label}</div>
                <div className="knum text-[12.5px] font-bold mt-0.5">
                  {envNum(env) != null ? fmt(envNum(env)) : <span className="muted text-[10px]">—</span>}
                </div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-2">
            {[
              ["NAV", d.nav, inr, TIPS.premium],
              ["Premium / discount", d.premium_discount_pct, (v: number) => pct(v), TIPS.premium],
              ["Tracking error", d.tracking_error_pct, (v: number) => `${v.toFixed(2)}%`, TIPS.te],
              ["Impact cost", d.impact_cost_pct, (v: number) => `${v.toFixed(3)}%`, TIPS.impact],
            ].map(([label, env, fmt, tip]: any) => (
              <div key={label} className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)" }}>
                <div className="muted text-[9px] font-bold uppercase tracking-wider">
                  {tip ? <MetricTip label={label} tip={tip}>{label}</MetricTip> : label}
                </div>
                <div className="knum text-[12.5px] font-bold mt-0.5">
                  {envNum(env) != null ? fmt(envNum(env)) : <span className="muted text-[10px]">—</span>}
                </div>
              </div>
            ))}
          </div>

          <div>
            <div className="flex items-center justify-between muted text-[10px] mb-1.5">
              <span className="font-bold uppercase tracking-[0.13em]">
                <MetricTip label="Liquidity score" tip={TIPS.liquidity} />
              </span>
              <span className="knum">{envNum(d.liquidity_score) ?? "—"}/100</span>
            </div>
            <div className="relative h-2 rounded-full overflow-hidden" style={{ background: "var(--line)" }}>
              <div className="absolute inset-y-0 left-0 rounded-full"
                   style={{ width: `${Math.max(0, Math.min(100, envNum(d.liquidity_score) || 0))}%`,
                            background: "linear-gradient(90deg,var(--down),var(--warn),var(--up))" }} />
            </div>
            <div className="flex justify-between muted text-[9.5px] mt-1">
              <span>Illiquid</span><span>Deep</span>
            </div>
          </div>
        </aside>
      </div>

      <section className="mb-6">
        <SectionTitle title="Returns ladder"
                    sub="Price returns from the stored five-year daily series. 3Y and 5Y are compound annual growth rates." />
        <StatGrid items={["1m", "3m", "6m", "1y", "3y", "5y"].map((k) => ({
          label: k === "1m" ? "1M" : k === "3m" ? "3M" : k === "6m" ? "6M" : k === "1y" ? "1Y" : k === "3y" ? "3Y CAGR" : "5Y CAGR",
          env: d.returns?.[k],
          fmt: (v: number) => pct(v),
          tip: TIPS.cagr,
        }))} />
      </section>

      <section className="grid lg:grid-cols-2 gap-3 mb-6">
        <div className="card p-4">
          <div className="text-[13px] font-bold mb-2">Tracking &amp; liquidity</div>
          <dl className="space-y-2 text-[12px]">
            {[
              ["Benchmark", d.benchmark || "—"],
              ["Tracking error", te != null ? `${te.toFixed(2)}%` : "Not available"],
              ["Impact cost", envNum(d.impact_cost_pct) != null ? `${Number(envNum(d.impact_cost_pct)).toFixed(3)}%` : "—"],
              ["Liquidity score", envNum(d.liquidity_score) != null ? `${envNum(d.liquidity_score)}/100` : "—"],
              ["Volume", envNum(d.volume) != null ? Number(envNum(d.volume)).toLocaleString("en-IN") : "—"],
              ["Turnover", envNum(d.turnover_cr) != null ? `₹${Number(envNum(d.turnover_cr)).toLocaleString("en-IN")} Cr` : "—"],
              ["History", `${Number(d.history_points || 0).toLocaleString("en-IN")} daily sessions`],
              ["Quote source", d.quote_source || "—"],
            ].map(([k, v]) => (
              <div key={k} className="flex items-start justify-between gap-4">
                <dt className="muted">{k}</dt>
                <dd className="text-right font-semibold" style={{ color: "var(--ink)" }}>{v}</dd>
              </div>
            ))}
          </dl>
          <p className="muted text-[10.5px] mt-3 leading-relaxed">{d.tracking_error_note}</p>
        </div>

        <div className="card p-4">
          <div className="text-[13px] font-bold mb-1">ETF vs index fund — true cost</div>
          <p className="muted text-[11px] leading-relaxed">
            Same gross index return for both wrappers. The ETF saves the TER gap but
            pays delivery brokerage, STT, DP and a modelled impact cost.
          </p>
          <div className="grid sm:grid-cols-2 gap-2 mt-3">
            <label className="block">
              <span className="muted text-[10px] font-bold uppercase tracking-wider">Amount ₹</span>
              <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="numeric"
                     className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                     style={{ color: "var(--ink)" }} />
            </label>
            <label className="block">
              <span className="muted text-[10px] font-bold uppercase tracking-wider">Years</span>
              <input value={years} onChange={(e) => setYears(e.target.value)} inputMode="decimal"
                     className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                     style={{ color: "var(--ink)" }} />
            </label>
            <label className="block">
              <span className="muted text-[10px] font-bold uppercase tracking-wider">Expected gross return %</span>
              <input value={expected} onChange={(e) => setExpected(e.target.value)} inputMode="decimal"
                     className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                     style={{ color: "var(--ink)" }} />
            </label>
            <label className="block">
              <span className="muted text-[10px] font-bold uppercase tracking-wider">ETF TER %</span>
              <input value={etfTer} onChange={(e) => setEtfTer(e.target.value)} inputMode="decimal"
                     className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                     style={{ color: "var(--ink)" }} />
            </label>
            <label className="block sm:col-span-2">
              <span className="muted text-[10px] font-bold uppercase tracking-wider">Index fund TER %</span>
              <input value={mfTer} onChange={(e) => setMfTer(e.target.value)} inputMode="decimal"
                     className="surface rounded-lg w-full mt-1 px-2.5 py-2 text-[12px] knum"
                     style={{ color: "var(--ink)" }} />
            </label>
          </div>
          <button onClick={runVs} disabled={busy}
                  className="btn-primary w-full justify-center !py-2 !text-[12px] mt-2">
            {busy ? "Calculating…" : "Compare true cost"}
          </button>
          {vsErr && <p className="text-[11.5px] text-down font-semibold mt-2">{vsErr}</p>}
          {vs && (
            <div className="mt-3 space-y-1.5 text-[12px]">
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                  <div className="muted text-[9px] font-bold uppercase tracking-wider">ETF after charges</div>
                  <div className="knum text-[15px] font-black mt-0.5">{inr(vs.etf_value_after_charges)}</div>
                </div>
                <div className="rounded-md px-2.5 py-2" style={{ border: "1px solid var(--line)", background: "var(--surface-2)" }}>
                  <div className="muted text-[9px] font-bold uppercase tracking-wider">Index fund</div>
                  <div className="knum text-[15px] font-black mt-0.5">{inr(vs.index_fund_value)}</div>
                </div>
              </div>
              <div className="flex justify-between"><span className="muted">ETF charges</span><span className="knum text-down">−{inr(vs.etf_charges?.total)}</span></div>
              <div className="flex justify-between pt-1.5" style={{ borderTop: "1px solid var(--line)" }}>
                <span className="muted font-semibold">ETF advantage</span>
                <span className={`knum font-black ${vs.advantage_etf >= 0 ? "text-up" : "text-down"}`}>{inr(vs.advantage_etf)}</span>
              </div>
              <p className="muted text-[10.5px] leading-relaxed">{vs.note}</p>
            </div>
          )}
        </div>
      </section>

      <section className="grid md:grid-cols-2 gap-3">
        <div className="card p-4">
          <div className="text-[13px] font-bold mb-2.5">ETF facts</div>
          <dl className="space-y-2 text-[12px]">
            {[
              ["Symbol", d.symbol],
              ["Category", d.category || "—"],
              ["Issuer", d.issuer || "—"],
              ["Benchmark", d.benchmark || "—"],
              ["Quote source", d.quote_source || "—"],
              ["History source", d.history_source || "—"],
              ["Data stamp", d.asof ? fmtDate(d.asof) : "—"],
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
          {(d.source_notes || []).map((n: string) => (
            <p key={n} className="muted text-[12px] leading-relaxed">{n}</p>
          ))}
          <p className="muted text-[11px] leading-relaxed">
            This is quantitative research, not investment advice. ETF prices can trade
            away from NAV, especially in less liquid schemes.
          </p>
        </div>
      </section>
    </div>
  );
}
